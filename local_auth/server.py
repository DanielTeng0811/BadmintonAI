"""Same-origin login service and authenticated HTTP/WebSocket reverse proxy."""
from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from pathlib import Path
import time

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web
from multidict import CIMultiDict
from yarl import URL

from .store import ADMIN, DOMAIN, SESSION_SECONDS, AuthError, Store, token_hash

STATIC = Path(__file__).parent / "static"
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
               "transfer-encoding", "upgrade", "content-length", "host", "cookie", "set-cookie"}


def create_app(database, upstream="http://gateway:8765", cookie_name="badminton_session"):
    store = Store(database)
    sockets = {}
    app = web.Application(client_max_size=38 * 1024 * 1024)
    app["store"] = store
    app["sockets"] = sockets

    def identity(request):
        return store.identity(request.cookies.get(cookie_name, ""))

    def guard_origin(request, *, required=False):
        origin = request.headers.get("Origin")
        if origin is None:
            if required:
                raise AuthError("缺少來源驗證，請重新整理頁面。", 403)
            return
        if origin != f"{request.scheme}://{request.host}":
            raise AuthError("不接受跨網站請求。", 403)

    @web.middleware
    async def security(request, handler):
        # The published service is local-only; reject hostile Host/DNS-rebinding requests.
        host = request.url.host
        if host not in {"localhost", "127.0.0.1", "::1", "auth", "auth-test"}:
            return web.json_response({"error": "不接受此主機名稱。"}, status=403)
        try:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                guard_origin(request, required=True)
            elif request.headers.get("Origin"):
                guard_origin(request)
            result = await handler(request)
        except AuthError as exc:
            result = web.json_response({"error": str(exc)}, status=exc.status)
        if not result.prepared:
            result.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                   "Referrer-Policy": "same-origin", "X-Frame-Options": "SAMEORIGIN"})
        return result

    app.middlewares.append(security)

    async def lifecycle(_app):
        async with ClientSession(timeout=ClientTimeout(total=180), auto_decompress=False) as client:
            app["client"] = client
            yield
        for entries in list(sockets.values()):
            for ws in list(entries):
                await ws.close(code=1001, message=b"Service restarting")

    app.cleanup_ctx.append(lifecycle)

    async def shutdown(_app):
        for entries in list(sockets.values()):
            for ws in list(entries):
                await ws.close(code=1001, message=b"Service restarting")

    app.on_shutdown.append(shutdown)

    async def close_sessions(*, token=None, name=None):
        for digest, entries in list(sockets.items()):
            for ws, user in list(entries.items()):
                if (token and digest == token_hash(token)) or (name and user == name):
                    await ws.close(code=1008, message=b"Signed out")

    async def payload(request):
        if request.content_type != "application/json" or len(await request.read()) > 4096:
            raise AuthError("請使用 JSON 表單。", 400)
        try:
            value = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise AuthError("表單格式不正確。") from None
        if not isinstance(value, dict):
            raise AuthError("表單格式不正確。")
        return value

    def logged_in(response, token):
        response.set_cookie(cookie_name, token, httponly=True, samesite="Strict", path="/", max_age=SESSION_SECONDS)
        return response

    async def auth_page(request):
        if request.path == "/auth/account" and not identity(request):
            raise web.HTTPFound("/auth/login")
        return web.FileResponse(STATIC / "index.html", headers={"Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})

    async def status(_request):
        return web.json_response({"ok": True, "setup_required": store.setup_required()})

    async def me(request):
        user = identity(request)
        return web.json_response({"user": {"username": user["username"], "role": user["role"]} if user else None,
                                  "setup_required": store.setup_required()})

    async def credentials(request):
        data = await payload(request)
        name, password = data.get("username", ""), data.get("password", "")
        buckets = ["auth-ip:" + (request.remote or "unknown"), "auth-user:" + str(name).lower()[:64]]
        store.limited(buckets)
        try:
            if request.path == "/auth/setup":
                await asyncio.to_thread(store.create, name, password, bootstrap=True)
                token = store.issue(ADMIN)
            elif request.path == "/auth/register":
                store.limited(["register:" + (request.remote or "unknown")], limit=10)
                name = await asyncio.to_thread(store.create, name, password)
                store.failure(["register:" + (request.remote or "unknown")])
                token = store.issue(name)
            else:
                token = await asyncio.to_thread(store.login, name, password)
        except AuthError:
            store.failure(buckets)
            raise
        old_token = request.cookies.get(cookie_name)
        if old_token:
            store.revoke(old_token)
            await close_sessions(token=old_token)
        return logged_in(web.json_response({"ok": True}), token)

    async def logout(request):
        token = request.cookies.get(cookie_name, "")
        store.revoke(token)
        await close_sessions(token=token)
        response = web.json_response({"ok": True}, headers={"Clear-Site-Data": '"cache", "storage"'})
        response.del_cookie(cookie_name, path="/")
        return response

    async def password(request):
        user = identity(request)
        if not user:
            raise AuthError("請先登入。", 401)
        data = await payload(request)
        bucket = ["password:" + user["username"]]
        store.limited(bucket)
        try:
            await asyncio.to_thread(store.change_password, user["username"], data.get("current", ""), data.get("password", ""))
        except AuthError:
            store.failure(bucket)
            raise
        await close_sessions(name=user["username"])
        response = web.json_response({"ok": True})
        response.del_cookie(cookie_name, path="/")
        return response

    async def users(request):
        user = identity(request)
        if not user or user["role"] != "admin":
            raise AuthError("僅管理員可操作。", 403)
        if request.method == "POST":
            data = await payload(request)
            if not isinstance(data.get("disabled"), bool):
                raise AuthError("缺少帳號狀態。")
            store.disable(data.get("username", ""), data["disabled"])
            await close_sessions(name=data["username"])
        return web.json_response({"users": store.users()})

    def forward_headers(request, user):
        headers = CIMultiDict()
        for key, value in request.headers.items():
            lower = key.lower()
            if lower in HOP_HEADERS or lower.startswith(("cf-", "x-forwarded-", "sec-websocket-")) or lower == "forwarded":
                continue
            headers.add(key, value)
        headers["Host"] = request.host
        headers["X-Forwarded-Proto"] = request.scheme
        headers["Cf-Access-Authenticated-User-Email"] = user["username"] + "@" + DOMAIN
        return headers

    async def proxy(request):
        user = identity(request)
        if not user:
            if request.path == "/" and request.headers.get("Upgrade", "").lower() != "websocket":
                raise web.HTTPFound("/auth/login")
            raise AuthError("請先登入。", 401)
        headers = forward_headers(request, user)
        bearer = request.headers.get("Authorization", "")
        token = bearer[7:] if bearer.startswith("Bearer ") else request.query.get("token", "")
        if token and not store.owns_gateway_token(token, user["username"]):
            raise AuthError("登入狀態已過期，請重新整理。", 401)
        url = URL(upstream + request.raw_path, encoded=True)
        if request.headers.get("Upgrade", "").lower() == "websocket":
            guard_origin(request, required=True)
            if not token:
                raise AuthError("缺少連線憑證。", 401)
            return await proxy_websocket(request, url, headers, user)
        if request.path.startswith("/auth/") or request.path.startswith("/cdn-cgi/"):
            raise AuthError("找不到頁面。", 404)
        try:
            async with app["client"].request(request.method, url, headers=headers, data=await request.read(), allow_redirects=False) as upstream_response:
                body = await upstream_response.read()
                if request.path == "/webui/bootstrap" and upstream_response.status == 200:
                    boot = json.loads(body)
                    store.grant_gateway_token(boot["token"], user["username"], boot.get("expires_in", 300))
                out_headers = CIMultiDict((k, v) for k, v in upstream_response.headers.items() if k.lower() not in HOP_HEADERS)
                out_headers["Cache-Control"] = "no-store"
                return web.Response(status=upstream_response.status, body=body, headers=out_headers)
        except (OSError, asyncio.TimeoutError):
            raise AuthError("聊天服務暫時無法連線，請稍後再試。", 502) from None

    async def proxy_websocket(request, url, headers, user):
        session_token = request.cookies[cookie_name]
        socket_key = token_hash(session_token)
        client = app["client"]
        try:
            upstream_ws = await client.ws_connect(url, headers=headers, max_msg_size=38 * 1024 * 1024, heartbeat=20)
        except Exception:
            raise AuthError("聊天連線失敗，請重新整理。", 502) from None
        ws = web.WebSocketResponse(max_msg_size=38 * 1024 * 1024, heartbeat=20)
        await ws.prepare(request)
        sockets.setdefault(socket_key, {})[ws] = user["username"]

        async def relay(source, target):
            async for msg in source:
                if not store.identity(session_token):
                    await ws.close(code=1008, message=b"Session expired")
                    break
                if msg.type == WSMsgType.TEXT:
                    await target.send_str(msg.data)
                elif msg.type == WSMsgType.BINARY:
                    await target.send_bytes(msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break

        async def expiry():
            await asyncio.sleep(max(0, user["expires"] - time.time()))
            await ws.close(code=1008, message=b"Session expired")

        tasks = [asyncio.create_task(relay(ws, upstream_ws)), asyncio.create_task(relay(upstream_ws, ws)), asyncio.create_task(expiry())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await upstream_ws.close()
            await ws.close()
            sockets.get(socket_key, {}).pop(ws, None)
            if not sockets.get(socket_key):
                sockets.pop(socket_key, None)
        return ws

    app.router.add_get("/auth/health", status)
    app.router.add_get("/auth/me", me)
    for path in ("/auth/login", "/auth/account", "/auth/register"):
        app.router.add_get(path, auth_page)
    for path in ("/auth/setup", "/auth/login", "/auth/register"):
        app.router.add_post(path, credentials)
    app.router.add_post("/auth/logout", logout)
    app.router.add_post("/auth/password", password)
    app.router.add_get("/auth/users", users)
    app.router.add_post("/auth/users", users)
    async def static_file(request):
        return web.FileResponse(STATIC / request.match_info["filename"])
    app.router.add_get("/auth/{filename:auth\\.css|auth\\.js}", static_file)
    app.router.add_route("*", "/{path:.*}", proxy)
    return app


if __name__ == "__main__":
    web.run_app(create_app(os.environ.get("AUTH_DATABASE", "/data/auth.db"),
                           os.environ.get("GATEWAY_URL", "http://gateway:8765"),
                           os.environ.get("AUTH_COOKIE_NAME", "badminton_session")),
                host="0.0.0.0", port=8080, access_log=None)

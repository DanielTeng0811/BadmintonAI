#!/usr/bin/env python3
"""Verify local auth against the real gateway with a disposable account DB; never call an LLM."""
import asyncio
import base64
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import tempfile
from urllib.parse import quote

from aiohttp import ClientSession, CookieJar, WSMsgType, web
from local_auth.server import create_app


async def main():
    checks, sessions, chats, fixtures = [], [], [], []
    suffix = secrets.token_hex(4)
    names = ["admin", "alice_" + suffix, "bob_" + suffix]
    password = secrets.token_urlsafe(24)
    origin = "http://127.0.0.1:18080"
    tmp = tempfile.TemporaryDirectory()
    app = create_app(Path(tmp.name) / "auth.db", "http://gateway:8765", cookie_name="auth_verification")
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 18080).start()

    def check(label, condition):
        checks.append({"id": label, "passed": bool(condition)})
        if not condition:
            raise AssertionError(label)

    async def request(client, method, path, status=200, **kwargs):
        async with client.request(method, origin + path, **kwargs) as response:
            body = await response.read()
            check(f"{method} {path.split('?')[0]} -> {status}", response.status == status)
            return json.loads(body) if response.content_type == "application/json" else body

    async def receive(ws, event):
        async with asyncio.timeout(15):
            while True:
                msg = await ws.receive()
                if msg.type != WSMsgType.TEXT:
                    raise AssertionError(f"WebSocket closed before {event}: {msg.type}")
                value = json.loads(msg.data)
                if value.get("event") == event:
                    return value

    async def connect(client, boot):
        ws = await client.ws_connect(origin + "/?token=" + boot["token"])
        await receive(ws, "ready")
        return ws

    async def new_chat(client, ws):
        await ws.send_json({"type":"new_chat"})
        cid = (await receive(ws, "attached"))["chat_id"]
        chats.append((client, "websocket:" + cid))
        return cid

    def urls(value):
        if isinstance(value, str):
            return [value] if value.startswith("/api/media/") else []
        if isinstance(value, dict):
            return sum((urls(v) for v in value.values()), [])
        if isinstance(value, list):
            return sum((urls(v) for v in value), [])
        return []

    try:
        for _ in names:
            sessions.append(ClientSession(cookie_jar=CookieJar(unsafe=True), headers={"Origin":origin}))
        admin, alice, bob = sessions
        await request(alice, "GET", "/api/sessions", 401)
        await request(alice, "GET", "/webui/bootstrap", 401)
        response = await alice.get(origin + "/", allow_redirects=False)
        check("anonymous_chat_redirects_to_login", response.status == 302 and response.headers.get("Location") == "/auth/login")
        response.release()
        await request(admin, "POST", "/auth/setup", json={"username":names[0], "password":password})
        await request(admin, "POST", "/auth/setup", 409, json={"username":names[0], "password":password})
        for name, client in zip(names[1:], sessions[1:]):
            await request(client, "POST", "/auth/register", json={"username":name, "password":password})
        boots = [await request(client, "GET", "/webui/bootstrap") for client in sessions]
        for name, boot in zip(names, boots):
            check("trusted_identity_" + name, boot["account"]["email"] == name + "@local.badminton")
        check("regular_users_cannot_manage_settings", not boots[1]["account"]["can_manage_settings"])
        auths = [{"Authorization":"Bearer " + boot["token"]} for boot in boots]
        await request(alice, "GET", "/api/settings", 403, headers=auths[1])
        await request(alice, "GET", "/auth/users", 403)
        await request(admin, "GET", "/api/settings", headers=auths[0])
        aws, bws = await connect(alice, boots[1]), await connect(bob, boots[2])
        aid, bid = await new_chat(alice, aws), await new_chat(bob, bws)
        # /help is a native command. It exercises transport/persistence with zero model calls.
        image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a8X8AAAAASUVORK5CYII="
        await aws.send_json({"type":"message", "chat_id":aid, "content":"/help", "media":[{"data_url":image,"name":"verification.png"}]})
        await receive(aws, "message")
        await bws.send_json({"type":"message", "chat_id":bid, "content":"/help"})
        await receive(bws, "message")
        akey, bkey = "websocket:" + aid, "websocket:" + bid
        # Native slash commands bypass user-message persistence. Seed a clearly owned
        # attachment fixture to exercise the real replay and account-bound media route.
        filename = "auth-verification-" + suffix + ".png"
        picture = Path("/gateway-state/media/websocket") / filename
        picture.parent.mkdir(parents=True, exist_ok=True)
        picture.write_bytes(base64.b64decode(image.split(",",1)[1]))
        fixtures.append(picture)
        transcript = Path("/gateway-state/webui") / ("websocket_" + aid + ".jsonl")
        with transcript.open("a") as file:
            file.write(json.dumps({"event":"user","chat_id":aid,"text":"ALICE PRIVATE ATTACHMENT",
                                   "media_paths":["/home/nanobot/.nanobot/media/websocket/"+filename]})+"\n")
        apath = "/api/sessions/" + quote(akey, safe="")
        bpath = "/api/sessions/" + quote(bkey, safe="")
        alist = await request(alice, "GET", "/api/sessions", headers=auths[1])
        blist = await request(bob, "GET", "/api/sessions", headers=auths[2])
        adminlist = await request(admin, "GET", "/api/sessions", headers=auths[0])
        check("alice_sees_only_own_chat", akey in {x["key"] for x in alist["sessions"]} and bkey not in {x["key"] for x in alist["sessions"]})
        check("bob_sees_only_own_chat", bkey in {x["key"] for x in blist["sessions"]} and akey not in {x["key"] for x in blist["sessions"]})
        check("admin_does_not_read_other_users_chats", akey not in {x["key"] for x in adminlist["sessions"]})
        await request(alice, "GET", apath + "/messages", headers=auths[1])
        athread = await request(alice, "GET", apath + "/webui-thread", headers=auths[1])
        await request(bob, "GET", apath + "/messages", 404, headers=auths[2])
        await request(bob, "GET", apath + "/webui-thread", 404, headers=auths[2])
        await request(bob, "GET", apath + "/delete", 404, headers=auths[2])
        await request(admin, "GET", apath + "/messages", 404, headers=auths[0])
        await request(bob, "GET", apath + "/messages", 404, headers={**auths[2], "Cf-Access-Authenticated-User-Email":names[1]+"@local.badminton"})
        await request(bob, "GET", "/api/sessions", 401, headers=auths[1])
        await bws.send_json({"type":"attach", "chat_id":aid})
        check("websocket_foreign_attach_rejected", (await receive(bws,"error"))["detail"] == "chat_forbidden")
        await bws.send_json({"type":"message", "chat_id":aid, "content":"/help"})
        check("websocket_foreign_write_rejected", (await receive(bws,"error"))["detail"] == "chat_forbidden")
        state = {"title_overrides":{akey:"ALICE PRIVATE TITLE"}, "pinned_keys":[akey]}
        await request(alice,"GET","/api/webui/sidebar-state/update?state=" + quote(json.dumps(state)),headers=auths[1])
        bstate = await request(bob,"GET","/api/webui/sidebar-state",headers=auths[2])
        check("sidebar_titles_and_pins_isolated", "ALICE PRIVATE TITLE" not in json.dumps(bstate) and akey not in json.dumps(bstate))
        awork = await request(alice,"GET","/api/workspaces",headers=auths[1])
        bwork = await request(bob,"GET","/api/workspaces",headers=auths[2])
        aroot, broot = awork["controls"]["managed_project_root"], bwork["controls"]["managed_project_root"]
        check("project_roots_are_per_account", aroot != broot and aroot and broot)
        await bws.send_json({"type":"new_chat","workspace_scope":{"project_path":aroot+"/verification","access_mode":"restricted"}})
        check("foreign_project_rejected", (await receive(bws,"error")).get("detail") is not None)
        media = urls(athread)
        check("attachment_has_signed_url", bool(media))
        await request(alice,"GET",media[0])
        await request(bob,"GET",media[0],401)
        await request(admin,"GET",media[0],401)
        # Remove the owned test histories before testing session revocation.
        await request(alice,"GET",apath+"/delete",headers=auths[1])
        await request(bob,"GET",bpath+"/delete",headers=auths[2])
        old_cookie = next(c.value for c in alice.cookie_jar if c.key == "auth_verification")
        async def closed(ws):
            async with asyncio.timeout(15):
                while (await ws.receive()).type == WSMsgType.TEXT:
                    pass
        close_task = asyncio.create_task(closed(aws))
        await request(alice,"POST","/auth/logout",json={})
        await close_task
        check("logout_closes_existing_websocket", aws.closed)
        await request(alice,"GET","/api/sessions",401,headers=auths[1])
        await request(alice,"GET","/api/sessions",401,headers={**auths[1],"Cookie":"auth_verification="+old_cookie})
        check("logout_revokes_stored_session", app["store"].identity(old_cookie) is None)
        close_task = asyncio.create_task(closed(bws))
        await request(admin,"POST","/auth/users",json={"username":names[2],"disabled":True})
        await close_task
        check("disable_closes_existing_websocket", bws.closed)
        await request(bob,"GET","/api/sessions",401,headers=auths[2])
        await request(bob,"POST","/auth/login",401,json={"username":names[2],"password":password})
        await request(admin,"POST","/auth/users",json={"username":names[2],"disabled":False})
        await request(bob,"POST","/auth/login",json={"username":names[2],"password":password})
        await request(bob,"POST","/auth/password",json={"current":password,"password":password+"new"})
        await request(bob,"GET","/api/sessions",401,headers=auths[2])
        await request(bob,"POST","/auth/login",401,json={"username":names[2],"password":password})
        await request(bob,"POST","/auth/login",json={"username":names[2],"password":password+"new"})
    except Exception as exc:
        checks.append({"id":"verification_error", "passed":False, "error":type(exc).__name__+": "+str(exc)[:200]})
        raise
    finally:
        # Each key here was created by this run. Preserve unrelated and legacy histories.
        for client, key in chats:
            index = sessions.index(client)
            try:
                fresh = await client.get(origin+"/webui/bootstrap")
                boot = await fresh.json()
                fresh.release()
                if "token" in boot:
                    response = await client.get(origin+"/api/sessions/"+quote(key,safe="")+"/delete",headers={"Authorization":"Bearer "+boot["token"]})
                    response.release()
            except Exception:
                pass
        for fixture in fixtures:
            fixture.unlink(missing_ok=True)
        for name in names[1:]:
            digest = hashlib.sha256((name+"@local.badminton").encode()).hexdigest()[:10]
            (Path("/gateway-state/webui") / ("sidebar-state."+name[:24]+"-"+digest+".json")).unlink(missing_ok=True)
        for client in sessions:
            await client.close()
        await runner.cleanup()
        tmp.cleanup()
        report = {"time":datetime.now(timezone.utc).isoformat(),"mode":"real_gateway_disposable_local_accounts",
                  "model_requests":0,"production_auth_database_modified":False,
                  "passed":sum(c["passed"] for c in checks),"total":len(checks),"checks":checks}
        out = Path("/results/auth-verification")
        out.mkdir(parents=True,exist_ok=True)
        path = out/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"-"+suffix+".json")
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        print(json.dumps({k:report[k] for k in ["passed","total","model_requests","production_auth_database_modified"]}))


if __name__ == "__main__":
    asyncio.run(main())

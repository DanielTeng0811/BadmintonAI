"""Account lifecycle and proxy boundary tests; no model or third-party account is used."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_auth.store import AuthError, Store, password_matches, token_hash

PASSWORD = "A-test-only-password-42"


def test_no_default_account_and_atomic_setup(tmp_path):
    store = Store(tmp_path / "auth.db")
    assert store.setup_required()
    with pytest.raises(AuthError):
        store.create("alice", PASSWORD)
    store.create("admin", PASSWORD, bootstrap=True)
    with pytest.raises(AuthError):
        store.create("admin", PASSWORD, bootstrap=True)
    store.create("alice", PASSWORD)
    with pytest.raises(AuthError):
        store.create("ALICE", PASSWORD)
    assert [u["role"] for u in store.users()] == ["admin", "user"]


def test_concurrent_first_setup_creates_only_one_admin(tmp_path):
    store = Store(tmp_path / "auth.db")
    def attempt():
        try:
            store.create("admin", PASSWORD, bootstrap=True)
            return True
        except AuthError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(lambda _: attempt(), range(2))) == 1
    assert len(store.users()) == 1


def test_passwords_and_tokens_are_hashed_and_sessions_persist(tmp_path):
    path = tmp_path / "auth.db"
    store = Store(path)
    store.create("admin", PASSWORD, bootstrap=True)
    token = store.login("admin", PASSWORD)
    with store.connect() as db:
        row = db.execute("SELECT password_hash FROM users").fetchone()[0]
        assert row != PASSWORD and password_matches(PASSWORD, row)
        assert db.execute("SELECT digest FROM sessions").fetchone()[0] == token_hash(token)
    assert PASSWORD.encode() not in path.read_bytes()
    assert token.encode() not in path.read_bytes()
    assert Store(path).identity(token)["username"] == "admin"
    store.revoke(token)
    assert store.identity(token) is None


def test_password_change_disable_and_expiry_revoke_sessions(tmp_path):
    store = Store(tmp_path / "auth.db")
    store.create("admin", PASSWORD, bootstrap=True)
    store.create("alice", PASSWORD)
    tokens = [store.login("alice", PASSWORD) for _ in range(2)]
    store.change_password("alice", PASSWORD, PASSWORD + "-new")
    assert all(store.identity(t) is None for t in tokens)
    with pytest.raises(AuthError):
        store.login("alice", PASSWORD)
    token = store.login("alice", PASSWORD + "-new")
    store.disable("alice", True)
    assert store.identity(token) is None
    with pytest.raises(AuthError):
        store.login("alice", PASSWORD + "-new")
    with pytest.raises(AuthError):
        store.disable("admin", True)
    store.disable("alice", False)
    token = store.login("alice", PASSWORD + "-new")
    with store.connect() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert store.identity(token) is None


def test_auth_rate_limit_and_token_owner_binding(tmp_path):
    store = Store(tmp_path / "auth.db")
    for _ in range(10):
        store.failure(["ip:test"])
    with pytest.raises(AuthError) as exc:
        store.limited(["ip:test"])
    assert exc.value.status == 429
    store.grant_gateway_token("gateway-secret", "alice", 300)
    assert store.owns_gateway_token("gateway-secret", "alice")
    assert not store.owns_gateway_token("gateway-secret", "bob")
    with store.connect() as db:
        db.execute("UPDATE gateway_tokens SET expires=?", (time.time() - 1,))
    assert not store.owns_gateway_token("gateway-secret", "alice")


def test_console_recovery_invalidates_previous_credentials(tmp_path):
    store = Store(tmp_path / "auth.db")
    store.create("admin", PASSWORD, bootstrap=True)
    token = store.login("admin", PASSWORD)
    store.reset_password("admin", PASSWORD + "-recovered")
    assert store.identity(token) is None
    with pytest.raises(AuthError):
        store.login("admin", PASSWORD)
    assert store.identity(store.login("admin", PASSWORD + "-recovered"))["role"] == "admin"


def test_proxy_auth_cookie_csrf_identity_and_logout(tmp_path):
    pytest.importorskip("aiohttp")
    from aiohttp import CookieJar, web
    from aiohttp.test_utils import TestClient, TestServer
    from local_auth.server import create_app

    async def scenario():
        async def backend(request):
            email = request.headers.get("Cf-Access-Authenticated-User-Email")
            if request.path == "/webui/bootstrap":
                return web.json_response({"token": "token-for-" + email, "expires_in": 300})
            return web.json_response({"email": email, "cookie": request.headers.get("Cookie")})
        upstream = web.Application()
        upstream.router.add_route("*", "/{path:.*}", backend)
        async with TestServer(upstream) as target:
            app = create_app(tmp_path / "auth.db", str(target.make_url("")).rstrip("/"))
            async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as admin:
                origin = str(admin.make_url("")).rstrip("/")
                headers = {"Origin": origin}
                assert (await admin.get("/api/sessions")).status == 401
                assert (await admin.get("/", allow_redirects=False)).status == 302
                assert (await admin.get("/auth/login")).status == 200
                assert (await admin.post("/auth/setup", json={"username":"admin", "password":PASSWORD})).status == 403
                response = await admin.post("/auth/setup", json={"username":"admin", "password":PASSWORD}, headers=headers)
                assert response.status == 200
                cookie = response.cookies["badminton_session"]
                assert cookie["httponly"] and cookie["samesite"] == "Strict"
                old_cookie = cookie.value
                assert (await admin.get("/auth/me")).status == 200
                spoof = {"Cf-Access-Authenticated-User-Email":"victim@example.com", "X-Forwarded-Proto":"https"}
                data = await (await admin.get("/test", headers=spoof)).json()
                assert data == {"email":"admin@local.badminton", "cookie":None}
                assert (await admin.get("/test", headers={"Host":"evil.example"})).status == 403
                assert (await admin.post("/auth/logout", json={}, headers={"Origin":"https://evil.example"})).status == 403
                boot = await (await admin.get("/webui/bootstrap")).json()
                token = boot["token"]
                async with TestClient(TestServer(create_app(tmp_path / "other.db", str(target.make_url("")).rstrip("/"))), cookie_jar=CookieJar(unsafe=True)) as other:
                    # Separate browser jars, same auth service for the real cross-account check below.
                    assert (await other.get("/api/sessions")).status == 401
                app["store"].create("alice", PASSWORD)
                alice_token = app["store"].login("alice", PASSWORD)
                admin.session.cookie_jar.clear()
                admin.session.cookie_jar.update_cookies({"badminton_session":alice_token}, response_url=admin.make_url("/"))
                assert (await admin.get("/api/sessions", headers={"Authorization":"Bearer " + token})).status == 401
                assert (await admin.get("/auth/users")).status == 403
                assert (await admin.post("/auth/users", json={"username":"admin", "disabled":True}, headers=headers)).status == 403
                assert (await admin.post("/auth/logout", json={}, headers=headers)).status == 200
                assert (await admin.get("/api/sessions")).status == 401
                assert app["store"].identity(alice_token) is None
                # The admin's distinct session was not revoked by Alice signing out.
                assert app["store"].identity(old_cookie)["username"] == "admin"
    asyncio.run(scenario())

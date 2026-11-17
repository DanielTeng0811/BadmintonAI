"""Local reels routing, account ownership and HTTP range delivery."""
import asyncio
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import badminton_gpt_reels as deployment
import local_reels_gateway as gateway
from local_auth.server import create_app


def test_gateway_job_ownership_and_unchanged_other_servers(tmp_path):
    path = tmp_path / "ledger.db"
    with patch.object(gateway, "_identity", return_value=("alice@local.badminton", path)):
        assert gateway.authorize("badminton-db", "query", {}) is None
        assert gateway.authorize(gateway.SERVER, "generate_reel", {}) is None
        gateway.record(gateway.SERVER, "generate_reel", json.dumps({"job_id": "test-1"}))
        for name in ("get_reel_status", "get_reel_result", "resume_reel"):
            assert gateway.authorize(gateway.SERVER, name, {"job_id": "test-1"}) is None
            assert gateway.authorize(gateway.SERVER, name, {"job_id": "../test-1"})
    with patch.object(gateway, "_identity", return_value=("bob@local.badminton", path)):
        assert "JOB_NOT_FOUND" in gateway.authorize(gateway.SERVER, "get_reel_result", {"job_id": "test-1"})
        try:
            gateway.record(gateway.SERVER, "generate_reel", "", {"job_id": "test-1"})
        except RuntimeError:
            pass
        else:
            raise AssertionError("Ownership cannot be overwritten")
    with patch.object(gateway, "_identity", return_value=(None, path)):
        assert "ACCOUNT_REQUIRED" in gateway.authorize(gateway.SERVER, "generate_reel", {})


def test_optional_deployment_does_not_change_default_configuration(tmp_path):
    with patch.object(deployment, "MARKER", tmp_path / "absent"):
        assert not deployment.enabled()
        deployment.configure()  # must not read/write runtime config while disabled
        assert not list(tmp_path.iterdir())
    wrapper = ROOT / "vendor/badmintonGPT/vendor/nanobot/nanobot/agent/tools/mcp.py"
    modified = gateway.patch_wrapper(wrapper.read_text())
    compile(modified, str(wrapper), "exec")
    assert "authorize_reel" in modified and "record_reel" in modified


def test_video_requires_owner_and_forwards_range_without_cookies(tmp_path):
    async def scenario():
        ledger = tmp_path / "ledger.db"
        with sqlite3.connect(ledger) as db:
            db.execute(gateway.SCHEMA)
            db.execute("INSERT INTO local_reel_jobs VALUES (?,?,?)", (gateway.SERVER, "test-1", "alice@local.badminton"))
        calls = []
        async def media(request):
            calls.append(dict(request.headers))
            assert request.headers.get("Range") == "bytes=2-5"
            assert "Cookie" not in request.headers
            return web.Response(status=206, body=b"2345", headers={
                "Content-Type": "video/mp4", "Content-Range": "bytes 2-5/10", "Accept-Ranges": "bytes"})
        service = web.Application()
        service.router.add_get("/files/test-1.mp4", media)
        async with TestServer(service) as backend:
            app = create_app(tmp_path / "auth.db", reels_upstream=str(backend.make_url("")).rstrip("/"), reels_ledger=ledger)
            app["store"].create("admin", "Test-password-12345", bootstrap=True)
            for name in ("alice", "bob"):
                app["store"].create(name, "Test-password-12345")
            async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
                route = "/reels/files/test-1.mp4"
                assert (await client.get(route)).status == 401
                def login(name):
                    client.session.cookie_jar.clear()
                    client.session.cookie_jar.update_cookies({"badminton_session": app["store"].issue(name)}, response_url=client.make_url("/"))
                login("bob")
                assert (await client.get(route)).status == 404
                assert not calls
                login("alice")
                response = await client.get(route, headers={"Range": "bytes=2-5"})
                assert response.status == 206 and await response.read() == b"2345"
                assert response.headers["Content-Range"] == "bytes 2-5/10"
                assert response.headers["Cache-Control"] == "private, no-store"
                assert len(calls) == 1
    asyncio.run(scenario())

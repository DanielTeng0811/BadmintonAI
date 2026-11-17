#!/usr/bin/env python3
"""Real local reels integration checks. MCP/HTTP modes make no GPT/TTS requests."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

MATCH = "Viktor_AXELSEN_LEE_Zii_Jia_EAST_VENTURES_Indonesia_Open_2022_Semifinals"
RESULT = Path("/app/local/results/reels-verification.json")


async def mcp_check():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from nanobot.agent.tools.mcp import MCPToolWrapper
    from nanobot.agent.tools.context import RequestContext, bind_request_context, reset_request_context

    report = {"time": datetime.now(timezone.utc).isoformat(), "model_requests": 0, "tts_requests": 0, "checks": {}}
    token = bind_request_context(RequestContext(channel="cli", chat_id="reels-verification",
                                               metadata={"account_email": "admin@local.badminton"}))
    try:
        async with streamablehttp_client("http://badminton-reels:8900/mcp", headers={"Host": "localhost:8900"}) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                definitions = {tool.name: tool for tool in (await session.list_tools()).tools}
                assert set(definitions) == {"list_matches", "generate_reel", "get_reel_status", "get_reel_result", "resume_reel"}
                report["checks"]["mcp_tools"] = True
                schema = definitions["generate_reel"].inputSchema["properties"]
                assert schema["reel_type"]["default"] == "news_report"
                assert schema["duration_target_sec"]["default"] == 90
                assert schema["enable_anchor"]["default"] is True
                assert "continuous" in schema["narration"]["enum"]
                report["checks"]["original_mcp_defaults"] = True
                wrappers = {name: MCPToolWrapper(session, "badminton-reels", tool, tool_timeout=60) for name, tool in definitions.items()}
                async def call(name, **arguments):
                    text = await wrappers[name].execute(**arguments)
                    if name == "list_matches":
                        try:
                            value = json.loads(text)
                            return value.get("result", value) if isinstance(value, dict) else value
                        except ValueError:
                            return text.splitlines()
                    return json.loads(text)
                catalog = await call("list_matches")
                # FastMCP wraps list returns as a result object in structured output,
                # while TextContent remains the JSON list consumed by this wrapper.
                assert MATCH in catalog
                report["checks"]["catalog"] = True
                async def finish(job):
                    async with asyncio.timeout(180):
                        while True:
                            status = await call("get_reel_status", job_id=job)
                            if status["state"] == "succeeded":
                                return await call("get_reel_result", job_id=job)
                            if status["state"] == "failed":
                                raise RuntimeError(json.dumps(status, ensure_ascii=False))
                            await asyncio.sleep(1)
                arguments = dict(match_name=MATCH, reel_type="rally_collection", rally_ids=["2_01_00"],
                                 duration_target_sec=30, max_highlights=1, narration="none", enable_anchor=False)
                planned = await call("generate_reel", **arguments, plan_only=True)
                plan = await finish(planned["job_id"])
                assert plan["plan_only"] and not plan["video_ready"] and not plan["video_url"]
                report["checks"]["plan_only"] = True
                generated = await call("generate_reel", **arguments)
                video = await finish(generated["job_id"])
                assert video["video_ready"] and video["selected_rally_ids"] == ["2_01_00"]
                assert video["checks"]["source_clips_complete"]
                assert video["video_url"].endswith("/reels/files/" + generated["job_id"] + ".mp4")
                report["checks"]["real_render_and_result"] = True
                report["job_id"] = generated["job_id"]
                report["video_url"] = video["video_url"]
                report["duration_sec"] = video["duration_sec"]
                other = bind_request_context(RequestContext(channel="cli", chat_id="reels-verification-other",
                    metadata={"account_email": "reels_verification_other@local.badminton"}))
                try:
                    refused = await call("get_reel_result", job_id=generated["job_id"])
                    assert refused["error_code"] == "JOB_NOT_FOUND"
                    report["checks"]["foreign_account_refused"] = True
                finally:
                    reset_request_context(other)
    finally:
        reset_request_context(token)
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


async def http_check():
    from aiohttp import ClientSession, CookieJar
    from aiohttp.test_utils import TestClient, TestServer
    from local_auth.server import create_app
    path = Path("/results/reels-verification.json")
    report = json.loads(path.read_text())
    route = "/reels/files/" + report["job_id"] + ".mp4"
    # Check the actual production auth route anonymously, then use an isolated
    # auth DB for logged-in streaming without modifying the user's credentials.
    async with ClientSession() as client:
        response = await client.get("http://auth:8080" + route)
        assert response.status == 401
        await response.read()
        report["checks"]["production_route_requires_login"] = True
    with tempfile.TemporaryDirectory() as directory:
        app = create_app(Path(directory) / "auth.db", reels_upstream="http://badminton-reels:8900",
                         reels_ledger="/gateway-state/accounts.db")
        password = uuid.uuid4().hex + "Test-password"
        app["store"].create("admin", password, bootstrap=True)
        app["store"].create("reels_other", password)
        async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
            for name, expected in (("reels_other", 404), ("admin", 206)):
                client.session.cookie_jar.clear()
                client.session.cookie_jar.update_cookies({"badminton_session": app["store"].issue(name)}, response_url=client.make_url("/"))
                response = await client.get(route, headers={"Range": "bytes=0-1023"})
                body = await response.read()
                assert response.status == expected
                if expected == 206:
                    assert len(body) == 1024 and b"ftyp" in body[:32]
                    assert response.headers["Content-Range"].startswith("bytes 0-1023/")
                    report["checks"]["owner_video_range_delivery"] = True
                else:
                    report["checks"]["foreign_video_refused"] = True
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


async def agent_check(test_model=None, credentials_stdin=False):
    from nanobot.agent.loop import AgentLoop
    from nanobot.accounts import ledger
    from nanobot.config.loader import load_config, resolve_config_env_vars
    cfg = resolve_config_env_vars(load_config())
    if credentials_stdin:
        credentials = json.loads(sys.stdin.read())
        cfg.providers.openai.api_key = credentials["api_key"]
        cfg.providers.openai.api_base = credentials.get("api_base") or "https://api.openai.com/v1"
    root = Path("/app/local/results/reels-agent-workspace")
    root.mkdir(parents=True, exist_ok=True)
    for name in ("SOUL.md", "AGENTS.md", "USER.md"):
        source = cfg.workspace_path / name
        if source.exists():
            shutil.copyfile(source, root / name)
    shutil.copytree(cfg.workspace_path / "skills", root / "skills", dirs_exist_ok=True)
    cfg.agents.defaults.workspace = str(root)
    loop = AgentLoop.from_config(cfg, **({"model": test_model} if test_model else {}))
    key = "cli:reels-verification-" + uuid.uuid4().hex
    ledger().claim(key, "admin@local.badminton")
    await loop._connect_mcp()
    try:
        prompt = (f"這是已授權的本機剪輯測試。請讀 badminton-reels 技能並查其比賽清單。"
                  f"接著為 {MATCH} 建立 rally_collection，rally_ids=['2_01_00']，"
                  "plan_only=true，narration=none，duration_target_sec=30，max_highlights=1，enable_anchor=false。"
                  "請實際呼叫工具建立一次，回覆真實 job_id 即可，不要產生語音或影片。")
        reply = await asyncio.wait_for(loop.process_direct(prompt, session_key=key), timeout=180)
        trace = loop.sessions.get_or_create(key).messages
        calls = [tc["function"]["name"] for msg in trace for tc in msg.get("tool_calls", [])]
        passed = (any(name.endswith("list_matches") and "reels" in name for name in calls)
                  and any(name.endswith("generate_reel") and "reels" in name for name in calls))
        report = {"model": test_model or cfg.resolve_preset().model, "passed": passed, "calls": calls,
                  "credentials": "reels_test_process_only" if credentials_stdin else "gateway_default",
                  "response": reply.content, "mode": "real_agent_real_model_plan_only"}
        (RESULT.parent / "reels-agent-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        if not passed:
            raise RuntimeError("The configured model did not complete the reels tool calls; see reels-agent-verification.json")
    finally:
        await loop.close_mcp()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mcp", "http", "agent"], required=True)
    parser.add_argument("--model", help="Test-process model override only; does not change deployment defaults")
    parser.add_argument("--credentials-stdin", action="store_true", help="Read test-only credentials from stdin; never persist them")
    args = parser.parse_args()
    asyncio.run(agent_check(args.model, args.credentials_stdin) if args.mode == "agent" else {"mcp": mcp_check, "http": http_check}[args.mode]())

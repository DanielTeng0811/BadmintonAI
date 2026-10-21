#!/usr/bin/env python3
"""Real MCP/data checks and an explicitly opt-in Luna evaluation inside the gateway."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

BASE = Path("/app/local")


def decode_result(result):
    if result.isError:
        raise RuntimeError(str(result.content))
    structured = getattr(result, "structuredContent", None)
    if structured and "rows" in structured:
        return structured
    text = "\n".join(b.text for b in result.content if hasattr(b, "text"))
    return json.loads(text)


def read_answer(content):
    match = re.search(r"```json\s*(.*?)```", content, re.S)
    return json.loads(match.group(1) if match else content)["rows"]


async def offline(bank):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from nanobot.config.loader import load_config, resolve_config_env_vars
    cfg = resolve_config_env_vars(load_config())
    checks = []
    checks.append({"id": "resolved_luna_configuration", "passed": (
        "${" not in cfg.resolve_preset().model and cfg.providers.openai.api_type == "responses"
    ), "model": cfg.resolve_preset().model, "api_type": cfg.providers.openai.api_type,
        "api_request_made": False})
    source = BASE / "source.db"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == bank["source_sha256"], "Oracle source changed"
    db = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    async with streamablehttp_client("http://badminton-db:8801/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            assert names == {"list_tables", "describe_table", "query"}, names
            checks.append({"id": "mcp_contract", "passed": True})
            for case in bank["cases"]:
                expected = case["expected"]
                assert [dict(r) for r in db.execute(case["source_sql"])] == expected, case["id"]
                result = decode_result(await session.call_tool("query", {"sql": case["target_sql"]}))
                checks.append({"id": case["id"], "passed": result.get("rows") == expected,
                               "actual": result, "expected": expected})
            for i, sql in enumerate(["DELETE FROM shots", "SELECT 1; DELETE FROM shots", "UPDATE matches SET name='x'"]):
                result = decode_result(await session.call_tool("query", {"sql": sql}))
                checks.append({"id": f"readonly_{i}", "passed": "error" in result})
            result = decode_result(await session.call_tool("query", {"sql": "SELECT * FROM shots"}))
            checks.append({"id": "row_limit", "passed": len(result["rows"]) == 200})
            result = decode_result(await session.call_tool("query", {
                "sql": "SELECT COUNT(*) AS n FROM shots WHERE hit_area IS NOT NULL OR landing_area IS NOT NULL"}))
            checks.append({"id": "no_invented_zone_mapping", "passed": result["rows"] == [{"n": 0}]})
    db.close()
    checks.append(await plumbing())
    return checks


async def plumbing():
    """Scripted provider exercises the real agent/tool loop. This is NOT model evaluation."""
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.loader import load_config, resolve_config_env_vars
    from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

    class ScriptedProvider(LLMProvider):
        def __init__(self):
            super().__init__()
            self.step = 0

        def get_default_model(self):
            return "scripted-plumbing-only"

        async def chat(self, messages, **kwargs):
            self.step += 1
            calls = [
                ("read_file", {"path": "skills/badminton-db/SKILL.md"}),
                ("read_file", {"path": "skills/data-analysis/SKILL.md"}),
                ("mcp_badminton-db_query", {"sql": "SELECT player,COUNT(*) AS n FROM shots WHERE match_name='legacy_match_1' GROUP BY player ORDER BY player"}),
                ("exec", {}),
                ("read_file", {"path": "skills/visualise/SKILL.md"}),
            ]
            if self.step <= len(calls):
                name, arguments = calls[self.step - 1]
                if self.step == 4:
                    result = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
                    rows = result["rows"]
                    # Build the command from the actual MCP response, never a frozen answer.
                    import shlex
                    code = 'import json; rows=' + repr(rows) + '; total=sum(r["n"] for r in rows); print(json.dumps({"rows":[{"player":r["player"],"n":r["n"],"pct":round(100*r["n"]/total,2)} for r in rows]}))'
                    arguments = {"command": "python3 -c " + shlex.quote(code)}
                return LLMResponse(content=None, tool_calls=[ToolCallRequest(str(self.step), name, arguments)])
            results = [m["content"] for m in messages if m["role"] == "tool"]
            if not results[3].rstrip().endswith("Exit code: 0"):
                raise RuntimeError("Python calculation failed: " + results[3][:300])
            calculated, _ = json.JSONDecoder().raw_decode(results[3].lstrip())
            data = calculated["rows"]
            bars = ''.join(f'<text x="10" y="{30+i*55}" fill="var(--color-text-primary, #202020)">{r["player"]}: {r["pct"]}%</text><rect x="100" y="{12+i*55}" width="{r["pct"]*3}" height="25" fill="#287b72"/>' for i, r in enumerate(data))
            chart = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 130" role="img" aria-label="Plumbing test: shot proportions">' + bars + '</svg>'
            return LLMResponse(content="離線工具流程驗證（固定步驟，未呼叫 Luna）。A＝Kento MOMOTA；B＝CHOU Tien Chen。\n```json\n" + json.dumps(calculated) + "\n```\n```visualizer\n" + chart + "\n```")

    cfg = resolve_config_env_vars(load_config())
    # A separate workspace/session store prevents test data from entering user conversations.
    import shutil
    root = BASE / "results/plumbing-workspace"
    root.mkdir(parents=True, exist_ok=True)
    for name in ("SOUL.md", "AGENTS.md", "USER.md"):
        src = cfg.workspace_path / name
        if src.exists():
            shutil.copy2(src, root / name)
    shutil.copytree(cfg.workspace_path / "skills", root / "skills", dirs_exist_ok=True)
    cfg.agents.defaults.workspace = str(root)
    # The sandbox must use the same workspace as the test instance.
    provider = ScriptedProvider()
    loop = AgentLoop.from_config(cfg, provider=provider, model=provider.get_default_model())
    key = "cli:plumbing-" + uuid.uuid4().hex
    await loop._connect_mcp()
    try:
        reply = await asyncio.wait_for(loop.process_direct("比較 legacy_match_1 的出手比例並畫圖。", session_key=key), timeout=90)
        content = reply.content if reply else ""
        actual = read_answer(content)
        expected = next(c for c in json.loads((BASE / "benchmark/cases.json").read_text())["cases"] if c["id"] == "chart")["expected"]
        calls = [tc["function"]["name"] for msg in loop.sessions.get_or_create(key).messages for tc in msg.get("tool_calls", [])]
        passed = actual == expected and "exec" in calls and "mcp_badminton-db_query" in calls and "```visualizer" in content
        (BASE / "results/plumbing-response.md").write_text(content)
        (BASE / "results/plumbing-trace.json").write_text(json.dumps(loop.sessions.get_or_create(key).messages, ensure_ascii=False, indent=2))
        return {"id": "agent_skills_mcp_python_chart", "passed": passed, "calls": calls,
                "provider": "scripted; no model quality claim", "actual": actual}
    finally:
        await loop.close_mcp()


async def live(bank):
    from nanobot.agent.loop import AgentLoop
    from nanobot.config.loader import load_config, resolve_config_env_vars
    cfg = resolve_config_env_vars(load_config())
    loop = AgentLoop.from_config(cfg)
    checks = []
    await loop._connect_mcp()
    try:
        for case in bank["cases"]:
            key = "cli:benchmark-" + uuid.uuid4().hex
            fields = list(case["expected"][0]) if case["expected"] else []
            prompt = case["prompt"] + '\n請依 skills 操作工具。最後用一個 json code fence 回傳 {"rows":[...]}，每列欄位為 ' + json.dumps(fields) + '，排序依識別欄位遞增。需要圖表時在 JSON 後加 visualizer。'
            try:
                reply = await asyncio.wait_for(loop.process_direct(prompt, session_key=key), timeout=180)
                content = reply.content if reply else ""
                actual = read_answer(content)
                trace = loop.sessions.get_or_create(key).messages
                calls = [tc["function"]["name"] for msg in trace for tc in msg.get("tool_calls", [])]
                skill_reads = [tc["function"]["arguments"] for msg in trace for tc in msg.get("tool_calls", []) if tc["function"]["name"] == "read_file"]
                read_db_skill = any("badminton-db/SKILL.md" in str(arg) for arg in skill_reads)
                passed = actual == case["expected"] and "mcp_badminton-db_query" in calls and read_db_skill
                if case["requires_chart"]:
                    passed = passed and "exec" in calls and "```visualizer" in content and any("visualise/SKILL.md" in str(arg) for arg in skill_reads)
                checks.append({"id": case["id"], "passed": passed, "actual": actual, "expected": case["expected"], "calls": calls, "response": content, "trace": trace})
            except Exception as exc:
                checks.append({"id": case["id"], "passed": False, "error": type(exc).__name__ + ": " + str(exc)[:300]})
    finally:
        await loop.close_mcp()
    return checks


def preview():
    """Publish the verified, explicitly scripted result as a local display-only session."""
    from nanobot.config.loader import load_config, resolve_config_env_vars
    from nanobot.session.manager import SessionManager
    from nanobot.webui.transcript import append_transcript_object, read_transcript_lines
    cfg = resolve_config_env_vars(load_config())
    manager = SessionManager(cfg.workspace_path)
    content = (BASE / "results/plumbing-response.md").read_text()
    key = "websocket:offline-verification-" + hashlib.sha256(content.encode()).hexdigest()[:8]
    session = manager.get_or_create(key)
    from nanobot import accounts
    if accounts.accounts_enabled():
        accounts.ledger().claim(key, "admin@local.badminton")
    prompt = "離線驗證預覽：legacy_match_1 出手比例（固定步驟測試，未呼叫 Luna）"
    if not session.messages:
        session.add_message("user", prompt)
        session.add_message("assistant", content)
        manager.save(session)
    if not read_transcript_lines(key):
        append_transcript_object(key, {"event": "user", "chat_id": "offline-verification", "text": prompt})
        append_transcript_object(key, {"event": "message", "chat_id": "offline-verification", "text": content})
        append_transcript_object(key, {"event": "turn_end", "chat_id": "offline-verification"})
    print("Created display preview: " + key)


async def main(mode):
    bank = json.loads((BASE / "benchmark/cases.json").read_text())
    checks = await (offline(bank) if mode == "offline" else live(bank))
    report = {"mode": mode, "time": datetime.now(timezone.utc).isoformat(),
              "model_validation": "not_run" if mode == "offline" else "live",
              "passed": sum(bool(c["passed"]) for c in checks), "total": len(checks), "checks": checks}
    directory = BASE / "results/benchmark-runs" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    path = directory / (mode + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"mode": mode, "passed": report["passed"], "total": report["total"], "report": str(path), "model_validation": report["model_validation"]}))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["offline", "live", "preview"], default="offline")
    mode = parser.parse_args().mode
    if mode == "preview":
        preview()
    else:
        asyncio.run(main(mode))

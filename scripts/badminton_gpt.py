#!/usr/bin/env python3
"""Local BadmintonGPT deployment; host commands require only Python's standard library."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/badmintonGPT"
RUNTIME = ROOT / ".runtime/badminton-gpt"
REVISION = "7cccbb18aba8bcfa096f22b923fb2aa16326e6ed"


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def compose(*args):
    return run(["docker", "compose", "--env-file", str(ROOT / ".env"),
                "-f", str(ROOT / "compose.badminton-gpt.yml"), *args])


def prepare_build():
    """Copy the pinned source and adapt only local prompts/example text before building."""
    destination = RUNTIME / "build"
    shutil.copytree(UPSTREAM, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "node_modules", "data"))
    for path in (destination / "vendor/nanobot/webui/src/i18n/locales").glob("*/common.json"):
        zh = path.parent.name.startswith("zh")
        content = json.loads(path.read_text())
        empty = content["thread"]["empty"]
        empty.setdefault("examples", {})
        greeting = "BadmintonGPT 本機資料分析 🏸" if zh else "BadmintonGPT · local match analysis 🏸"
        empty["greetings"] = dict.fromkeys(empty["greetings"], greeting)
        empty["examples"]["label"] = "先設定可用的 Luna API 金鑰，再試試以下問題" if zh else "Configure your Luna API key, then try these questions"
        examples = {
            "data": ("資料範圍", "列出目前資料庫的所有比賽紀錄、球員，以及每筆紀錄的拍數。", "Dataset catalog", "List all match records, their players and shot counts in the current database."),
            "reel": ("致勝球統計", "legacy_match_5 兩位球員各有幾拍直接致勝球？", "Winner counts", "How many shot winners did each player hit in legacy_match_5?"),
            "chart": ("球種圖表", "畫長條圖呈現 legacy_match_3 的球種次數分布。", "Shot distribution", "Draw a bar chart of shot-type counts in legacy_match_3."),
            "analysis": ("球員比較", "計算 legacy_match_1 兩位球員各自的出手次數與百分比。", "Player comparison", "Calculate each player's shot count and percentage in legacy_match_1."),
            "search": ("回合統計", "legacy_match_6 每局各有幾個回合？", "Rally counts", "How many rallies are in each set of legacy_match_6?"),
        }
        for key, (zt, zp, et, ep) in examples.items():
            empty["examples"][key] = {"title": zt if zh else et, "prompt": zp if zh else ep}
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    skill = destination / "skills/badminton-db/SKILL.md"
    text = skill.read_text()
    position = text.index("# badminton-db playbook")
    note = """# Local dataset coverage (overrides historical examples below)

This deployment has 5 catalog records (legacy_match_1, legacy_match_3,
legacy_match_5, legacy_match_6, legacy_match_7), 5204 shots and 409 rallies.
A = Kento MOMOTA; B = CHOU Tien Chen. Query matches.name / player_a / player_b
for the actual catalog. Tournament/year/round and analyze_match_id are NULL.
There are no videos, remote advanced analysis tools, or compatible zone labels.
Historical counts and match names in the upstream examples below are examples,
not available data. Never interpret NULL as zero. Use existing match_name values.
Rally IDs preserve original set/rally numbers and do not identify playable clips.

"""
    skill.write_text(text[:position] + note + text[position:])
    from badminton_gpt_account_overlay import apply
    apply(destination)
    print(f"Prepared build context from pinned upstream: {destination}")


def setup():
    if not (UPSTREAM / "nanobot/config.json").exists():
        run(["git", "submodule", "update", "--init", "vendor/badmintonGPT"])
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise RuntimeError(f"Unexpected upstream revision {revision}; expected {REVISION}")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    (RUNTIME / "data").mkdir(exist_ok=True)
    if not (ROOT / ".env").exists():
        (ROOT / ".env").write_text("NANOBOT_MODEL=gpt-6-luna\nOPENAI_API_KEY=\n")
        (ROOT / ".env").chmod(0o600)
    cfg = json.loads((UPSTREAM / "nanobot/config.json").read_text())
    cfg["agents"]["defaults"].update(
        timezone="Asia/Taipei", botName="BadmintonGPT", botIcon="🏸",
        reasoningEffort="low", maxToolIterations=40,
    )
    cfg["providers"]["openai"].update(apiBase="${OPENAI_API_BASE}", apiType="responses")
    cfg["gateway"].setdefault("heartbeat", {})["enabled"] = False
    # This local reproduction has no credentials for the lab's three remote services.
    # Remove both their tools and their skills; never advertise unavailable capabilities.
    cfg["tools"]["mcpServers"] = {k: v for k, v in cfg["tools"]["mcpServers"].items()
                                      if k == "badminton-db"}
    cfg["agents"]["defaults"]["disabledSkills"] += [
        "badminton-analyze", "badminton-reels", "badminton-video-retrieval",
        "long-mcp-job", "cron", "github",
    ]
    # Keep the original provider factory, agent loop, MCP transport and visualizer intact.
    # There is a single selectable model; old provider presets are irrelevant here.
    cfg["modelPresets"] = {}
    cfg.pop("model_presets", None)
    cfg["providers"]["custom"] = {"apiKey": "", "apiBase": None, "apiType": "auto"}
    (RUNTIME / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    soul = (UPSTREAM / "nanobot/workspace/SOUL.md").read_text()
    start = soul.index("## Tool routing")
    end = soul.index("## Execution rules")
    routing = """## Local reproduction: available data and routing

This installation uses the original nanobot agent loop, badminton-db MCP,
data-analysis skill, and visualise skill. Read the relevant SKILL.md before using it.

- Database questions: read badminton-db, inspect matches/rallies/shots with
  list_tables/describe_table/query. Use actual catalog values, not example match names.
- Numerical analysis: retrieve data through MCP, then calculate with python3 -c
  using the data-analysis playbook. Scope each match by match_name.
- Charts: read visualise and output HTML/SVG in a visualizer code fence.
- External badminton facts: use web search and cite the sources.
- Advanced analysis, clip search and highlight generation are unavailable here.
  Never call their tools, invent a URL, or infer missing advanced metrics.

The legacy import contains five separate records named legacy_match_1, _3, _5,
_6 and _7. Both players are Kento MOMOTA (A) and CHOU Tien Chen (B). Names do
not establish tournament, date, round, or a real-world match identity; those
metadata fields remain NULL. Distinguish these records by name. No videos exist.
The source uses incompatible court-zone codes, so hit_area/landing_area are NULL;
do not interpret zones. Rest time and movement metrics are not supplied.

First query the catalog: its rows define the actual coverage. The historical
counts in the original skill examples (188/244 matches) do not describe this DB.
Always present unknown or unavailable values honestly. A/B map to player_a/player_b.
Use only SELECT via MCP, with match_name for a specific match. Points won by a
shot type use win_reason IS NOT NULL, not getpoint_player alone.

"""
    (RUNTIME / "SOUL.md").write_text(soul[:start] + routing + soul[end:])
    (RUNTIME / "deployment.json").write_text(json.dumps({
        "upstream": "https://github.com/NYCU-ADSL/badmintonGPT", "revision": REVISION,
        "model": "${NANOBOT_MODEL:-gpt-6-luna}", "api": "responses",
        "disabled_remote_services": ["badminton-analyze", "badminton-video-retrieval", "badminton-reels"],
        "model_validation": "pending_user_api_key",
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Prepared {RUNTIME}; no model request was made.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["setup", "build", "ingest", "up", "down", "status", "logs", "verify", "benchmark", "preview", "verify-auth"])
    p.add_argument("--live", action="store_true", help="Explicitly run paid model evaluation")
    args = p.parse_args()
    if args.command == "setup":
        setup()
    elif args.command == "build":
        setup()
        prepare_build()
        compose("build")
    elif args.command == "ingest":
        setup()
        run([sys.executable, str(ROOT / "scripts/import_badminton_gpt_data.py")])
    elif args.command == "up":
        setup()
        if not (RUNTIME / "data/badminton.db").exists():
            raise RuntimeError("Database missing. Run: python3 scripts/badminton_gpt.py ingest")
        compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "180")
        print("BadmintonGPT: http://127.0.0.1:8765 (Luna requires your new API key)")
    elif args.command == "verify":
        compose("exec", "-T", "gateway", "python3", "/app/local/benchmark.py", "--mode", "offline")
    elif args.command == "benchmark":
        compose("exec", "-T", "gateway", "python3", "/app/local/benchmark.py", "--mode", "live" if args.live else "offline")
    elif args.command == "preview":
        compose("exec", "-T", "gateway", "python3", "/app/local/benchmark.py", "--mode", "preview")
    elif args.command == "verify-auth":
        compose("--profile", "auth-test", "run", "--rm", "auth-test")
    elif args.command == "status":
        compose("ps")
    elif args.command == "logs":
        compose("logs", "--tail", "80")
    else:
        compose("down")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

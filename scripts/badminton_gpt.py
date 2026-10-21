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


def dataset_context():
    manifest_path=RUNTIME / 'data/manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if manifest.get('dataset')=='shuttleset_merged':
        return f'''This installation contains the deduplicated ShuttleSet + ShuttleSet22:
{manifest['matches']} matches, {manifest['shots']} distinct shot annotations and {manifest['rallies']} rallies, spanning 2018–2022.
Query the live catalog; historical counts in the upstream examples do not apply.
A is each match's winner, B its loser; always join matches.player_a/player_b.
Matches include tournament, round, year, match_date, and video_url (43 external
YouTube links, availability unverified). Links are source videos, not local clips:
rallies.has_video=0 and video_filename=NULL. Never invent a clip or run reels.
Use match_links for source URLs; do not fetch/download them automatically.
Full source coordinates, frame_num, timestamp_seconds, flaw and original area
codes are retained in shot_details, joined by shot_id. source_hit_area and
source_landing_area use the dataset's grid; upstream shots.hit_area/landing_area
remain NULL until that grid is verified. Do not treat raw camera pixels as meters.
shot_sources preserves every raw row and source; datasets, match_sources and
match_homographies preserve provenance. Count shots, not shot_sources, because
the latter includes duplicate source copies. A repeated ball_round with distinct
frames is retained and flagged in data_quality_issues; shot_id identifies rows.
Raw flawed/unknown annotations remain included; state filters explicitly.
legacy_match_aliases resolves the old five processed records to full matches.
legacy_matches/legacy_shots/legacy_rallies retain the old transformed subset;
exclude them from current totals. An old name such as legacy_match_1 is an alias,
not another match. Existing saved results reflect the earlier subset.
Rally frame bounds are observed shot extrema, not validated video boundaries.
win_reason IS NOT NULL includes opponent errors; for annotated landing winners
use win_reason='落地致勝'. getpoint_player records the point winner, which may
differ from the player who hit the final shot. No remote advanced analysis exists.
'''
    return '''This is the historical five-record processed subset: 5204 shots and
409 rallies, legacy_match_1/3/5/6/7. A=Kento MOMOTA, B=CHOU Tien Chen.
Tournament/date/round are unknown, with no video or compatible zone mapping.
Query the actual catalog and never assume the upstream example coverage.
'''


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
            "reel": ("影片來源", "哪些比賽有原始影片網址？請保留來源連結並說明尚未驗證播放狀態。", "Video sources", "List original video URLs and note that availability has not been verified."),
            "chart": ("球種圖表", "畫長條圖呈現 2022 年所有比賽的球種次數分布。", "Shot distribution", "Draw a bar chart of shot-type counts across the 2022 matches."),
            "analysis": ("球員比較", "計算 2019 福州公開賽男單決賽兩位球員的出手次數與百分比。", "Player comparison", "Compare player shot counts and percentages in the 2019 Fuzhou Open men's singles final."),
            "search": ("年份統計", "依年份列出目前資料庫的比賽數。", "Yearly catalog", "Count the available matches by year."),
        }
        for key, (zt, zp, et, ep) in examples.items():
            empty["examples"][key] = {"title": zt if zh else et, "prompt": zp if zh else ep}
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
    skill = destination / "skills/badminton-db/SKILL.md"
    text = skill.read_text()
    position = text.index("# badminton-db playbook")
    note = '# Local dataset coverage (overrides historical examples below)\n\n'+dataset_context()+'\n'
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

First query the catalog: its rows define the actual coverage. The historical
counts in the original skill examples (188/244 matches) do not describe this DB.
Always present unknown or unavailable values honestly. A/B map to player_a/player_b.
Use only SELECT via MCP, with match_name for a specific match. Points won by a
shot type must distinguish the hitter from the point winner.

"""
    (RUNTIME / "SOUL.md").write_text(soul[:start] + routing + dataset_context()+'\n' + soul[end:])
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
        # Frozen expectations come from a separate CSV reader, before changing the live DB.
        run([sys.executable, str(ROOT / 'scripts/create_shuttleset_benchmark.py'), '--verify'])
        run([sys.executable, str(ROOT / 'scripts/import_shuttleset_data.py')])
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

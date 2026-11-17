"""Opt-in local reels deployment; credentials stay in the sibling project's .env."""
import json
from pathlib import Path
import shutil
import subprocess

from local_reels_gateway import patch_wrapper

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime/badminton-gpt"
MARKER = RUNTIME / "local-reels.json"
DIRECTORY = RUNTIME / "reels"


def enabled():
    return MARKER.is_file()


def enable(path):
    source = Path(path).expanduser().resolve()
    for required in (".env", "Dockerfile", "src/badminton/mcp_server.py"):
        if not (source / required).is_file():
            raise RuntimeError(f"Missing {source / required}")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({"source": str(source)}, indent=2) + "\n")


def test_credentials():
    """Read only the existing reels credentials, passed to the test via stdin."""
    source = Path(json.loads(MARKER.read_text())["source"])
    code = ("from badminton.config import Config; import json; "
            "c=Config(); print(json.dumps({'api_key':c.openai_api_key,'api_base':c.openai_base_url}))")
    result = subprocess.run(["uv", "run", "--locked", "python", "-c", code], cwd=source,
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Could not load reels test credentials; check its uv environment")
    value = json.loads(result.stdout)
    if not value.get("api_key"):
        raise RuntimeError("Missing reels OpenAI API key")
    return json.dumps(value)


def configure():
    if not enabled():
        return
    source = Path(json.loads(MARKER.read_text())["source"])
    DIRECTORY.mkdir(exist_ok=True)
    wrapper = ROOT / "vendor/badmintonGPT/vendor/nanobot/nanobot/agent/tools/mcp.py"
    (DIRECTORY / "mcp.py").write_text(patch_wrapper(wrapper.read_text()))
    shutil.copyfile(ROOT / "scripts/local_reels_gateway.py", DIRECTORY / "local_reels.py")
    shutil.copyfile(ROOT / "docs/badminton-reels-skill.md", DIRECTORY / "SKILL.md")
    (DIRECTORY / "Dockerfile").write_text('''FROM badmintonai-gateway:7cccbb1
COPY mcp.py /usr/local/lib/python3.12/site-packages/nanobot/agent/tools/mcp.py
COPY local_reels.py /usr/local/lib/python3.12/site-packages/nanobot/local_reels.py
''')
    overlay = {"services": {
        "gateway": {"image": "badmintonai-gateway:local-reels-v1", "build": {"context": str(DIRECTORY)},
                    "depends_on": {"badminton-reels": {"condition": "service_healthy"}},
                    "volumes": [str(DIRECTORY / "SKILL.md") + ":/app/skills/badminton-reels/SKILL.md:ro",
                                str(ROOT / "scripts/test_badminton_gpt_reels_live.py") + ":/app/local/reels-verification.py:ro"]},
        "auth": {"environment": {"REELS_UPSTREAM": "http://badminton-reels:8900",
                                 "REELS_LEDGER_PATH": "/gateway-state/accounts.db"},
                 "volumes": ["badminton_state:/gateway-state:ro"]},
        "badminton-reels": {"image": "badmintonai-reels:local-v2", "build": {"context": str(source)},
                            "env_file": [str(source / ".env")], "restart": "unless-stopped",
                            "environment": {"PUBLIC_BASE_URL": "http://127.0.0.1:${BADMINTONGPT_PORT:-8765}/reels",
                                            "MCP_HOST": "0.0.0.0", "MCP_PORT": "8900", "MAX_CONCURRENT_JOBS": "1",
                                            "DATA_DIR": "/app/data", "OUTPUT_DIR": "/app/output"},
                            "volumes": ["reels_output:/app/output", str(source / "data") + ":/app/data"],
                            "expose": ["8900"]},
        "auth-test": {"volumes": [str(ROOT / "scripts/test_badminton_gpt_reels_live.py") + ":/app/reels-verification.py:ro"]},
    }, "volumes": {"reels_output": {}}}
    (DIRECTORY / "compose.json").write_text(json.dumps(overlay, indent=2) + "\n")
    config_path = RUNTIME / "config.json"
    config = json.loads(config_path.read_text())
    config["tools"]["mcpServers"]["badminton-reels"] = {
        "type": "streamableHttp", "url": "http://badminton-reels:8900/mcp",
        "headers": {"Host": "localhost:8900"}, "toolTimeout": 60,
        "enabledTools": ["list_matches", "generate_reel", "get_reel_status", "get_reel_result", "resume_reel"],
    }
    disabled = config["agents"]["defaults"]["disabledSkills"]
    config["agents"]["defaults"]["disabledSkills"] = [x for x in disabled if x != "badminton-reels"]
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    soul_path = RUNTIME / "SOUL.md"
    soul = soul_path.read_text().replace(
        "- Advanced analysis, clip search and highlight generation are unavailable here.\n  Never call their tools, invent a URL, or infer missing advanced metrics.",
        "- Highlight generation is available through the LOCAL badminton-reels MCP. Read badminton-reels/SKILL.md.\n"
        "- Advanced analysis and the separate remote clip-search service remain unavailable. Do not invent advanced metrics.")
    soul += '''
## Explicitly enabled local reels service
For an explicit request to generate a video, the local badminton-reels service
may download authorized HF rally clips. This overrides the no-automatic-download
restriction only for that requested job. Its catalog is separate: use its
list_matches before generation; never assume every DB row has supported clips.
Read badminton-reels/SKILL.md, submit the requested type, poll status, retrieve
the result and return the actual video_url as a video Markdown attachment.
Original news_report defaults remain unchanged. Continuous commentary is an
option for the new modes; do not assume all reels need short narration.
Do not claim exact hit/audio synchronization or independent visual verification.
'''
    soul_path.write_text(soul)
    deployment_path = RUNTIME / "deployment.json"
    deployment = json.loads(deployment_path.read_text())
    deployment["disabled_remote_services"] = [x for x in deployment["disabled_remote_services"] if x != "badminton-reels"]
    deployment["local_reels"] = {"enabled": True, "source": str(source), "account_scoped": True}
    deployment_path.write_text(json.dumps(deployment, ensure_ascii=False, indent=2) + "\n")

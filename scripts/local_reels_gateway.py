"""Account ownership for the opt-in local reels MCP (installed into nanobot)."""
from __future__ import annotations

import json
import re
import sqlite3

SERVER = "badminton-reels"
JOB = re.compile(r"[A-Za-z0-9_-]{1,240}\Z")
SCHEMA = """CREATE TABLE IF NOT EXISTS local_reel_jobs (
server TEXT NOT NULL, job_id TEXT NOT NULL, email TEXT NOT NULL,
PRIMARY KEY (server, job_id))"""


def _identity():
    from nanobot.accounts import current_account_email, ledger
    return current_account_email(), ledger().path


def authorize(server, tool, arguments):
    if server != SERVER:
        return None
    email, path = _identity()
    if not email:
        return json.dumps({"error": "Authenticated account required", "error_code": "ACCOUNT_REQUIRED"})
    if tool in {"list_matches", "generate_reel"}:
        return None
    job = arguments.get("job_id", "")
    if not isinstance(job, str) or not JOB.fullmatch(job):
        return json.dumps({"error": "Unknown job", "error_code": "JOB_NOT_FOUND"})
    with sqlite3.connect(path, timeout=30) as db:
        db.execute(SCHEMA)
        owner = db.execute("SELECT email FROM local_reel_jobs WHERE server=? AND job_id=?", (server, job)).fetchone()
    if not owner or owner[0] != email:
        return json.dumps({"error": "Unknown job", "error_code": "JOB_NOT_FOUND"})
    return None


def record(server, tool, text, structured=None):
    if server != SERVER or tool != "generate_reel":
        return
    value = structured
    if not isinstance(value, dict):
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            return
    job = value.get("job_id")
    if not isinstance(job, str) or not JOB.fullmatch(job):
        return
    email, path = _identity()
    if not email:
        raise RuntimeError("Cannot attribute reel to an account")
    with sqlite3.connect(path, timeout=30) as db:
        db.execute(SCHEMA)
        db.execute("INSERT OR IGNORE INTO local_reel_jobs VALUES (?,?,?)", (server, job, email))
        owner = db.execute("SELECT email FROM local_reel_jobs WHERE server=? AND job_id=?", (server, job)).fetchone()
        if owner[0] != email:
            raise RuntimeError("Reel ownership conflict")


def patch_wrapper(source: str) -> str:
    before = "        for attempt in range(2):  # At most 1 retry\n"
    after = """        from nanobot.local_reels import authorize as authorize_reel
        refusal = authorize_reel(self._server_name, self._original_name, kwargs)
        if refusal is not None:
            return refusal

""" + before
    before_record = "                record_mcp_result(\n"
    after_record = """                from nanobot.local_reels import record as record_reel
                record_reel(self._server_name, self._original_name, text,
                            getattr(result, "structuredContent", None))
""" + before_record
    for old, new in ((before, after), (before_record, after_record)):
        if source.count(old) != 1:
            raise RuntimeError("Pinned MCP ownership overlay no longer matches")
        source = source.replace(old, new, 1)
    return source

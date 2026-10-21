#!/usr/bin/env python3
"""Import the existing five-record dataset into the pinned upstream schema, with provenance."""
from __future__ import annotations

import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/processed/processed_new_3.db"
TARGET = ROOT / ".runtime/badminton-gpt/data/badminton.db"


def upstream_schema():
    tree = ast.parse((ROOT / "vendor/badmintonGPT/mcps/badminton-db/ingest.py").read_text())
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DDL" for t in n.targets))


def build(source=SOURCE, target=TARGET):
    source, target = Path(source), Path(target)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = [dict(r) for r in src.execute('SELECT * FROM match_data ORDER BY match_id, "set", rally, ball_round')]
    src.close()
    if not rows:
        raise ValueError("The source dataset is empty")
    score_fields = [k for k in rows[0] if k.endswith("_score")]
    if len(score_fields) != 2:
        raise ValueError("Expected exactly two explicit player score columns")
    players = [k.removesuffix("_score") for k in score_fields]
    ab = dict(zip(players, ("A", "B")))
    if any(r["player"] not in ab or r["opponent"] not in ab for r in rows):
        raise ValueError("Unknown player: a stable A/B mapping cannot be established")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".building.db")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(upstream_schema())
    # Upstream references matches.name but declares only folder as a primary key.
    # A unique index makes those existing foreign keys enforceable by SQLite.
    db.execute("CREATE UNIQUE INDEX idx_matches_name ON matches(name)")
    ids = sorted({int(r["match_id"]) for r in rows})
    for mid in ids:
        name = f"legacy_match_{mid}"
        db.execute("INSERT INTO matches(folder,name,player_a,player_b,source) VALUES (?,?,?,?,?)",
                   (name + ".mp4", name, *players, "badmintonai_processed_new_3"))
    groups = {}
    for r in rows:
        mid, set_no, rally = int(r["match_id"]), int(r["set"]), int(r["rally"])
        name = f"legacy_match_{mid}"
        sa, sb = (int(r[k]) if r[k] is not None else None for k in score_fields)
        # Court zones use a different schema; leaving NULL avoids a false 1–16 mapping.
        db.execute("INSERT INTO shots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            name, set_no, rally, r["ball_round"], ab[r["player"]], r["server"], r["type"],
            r["aroundhead"], r["backhand"], None, None, r["lose_reason"] or None,
            r["win_reason"] or None, ab.get(r["getpoint_player"]), sa, sb,
        ))
        groups.setdefault((name, set_no, rally), []).append(r)
    for (name, set_no, rally), rr in groups.items():
        first = rr[0]
        sa, sb = (int(first[k]) if first[k] is not None else None for k in score_fields)
        # Imported identifiers preserve the original rally number; these are NOT video IDs.
        rid = f"{set_no}_legacy_{rally}"
        frames = [int(r["frame_num"]) for r in rr if r["frame_num"] is not None]
        db.execute("INSERT INTO rallies VALUES (?,?,?,?,?,?,?,?,?)", (
            name, rid, set_no, sa, sb, min(frames) if frames else None,
            max(frames) if frames else None, 0, None,
        ))
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    db.commit()
    db.close()
    tmp.replace(target)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "upstream_revision": "7cccbb18aba8bcfa096f22b923fb2aa16326e6ed",
        "matches": len(ids), "shots": len(rows), "rallies": len(groups),
        "player_mapping": ab, "match_shots": dict(Counter(f"legacy_match_{int(r['match_id'])}" for r in rows)),
        "limitations": ["not the gated upstream HF dataset", "tournament/date/round unknown",
                         "no video or remote analytics", "court zones omitted: incompatible numbering",
                         "frame bounds are annotated shots, not playable clip boundaries",
                         "records cannot establish distinct real-world match identities"],
    }
    target.with_name("manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


if __name__ == "__main__":
    build()

"""Protect the source-to-upstream boundary and the independent benchmark oracle."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("badminton_gpt_import", ROOT / "scripts/import_badminton_gpt_data.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    target = tmp_path_factory.mktemp("badminton-gpt") / "badminton.db"
    manifest = importer.build(target=target)
    db = sqlite3.connect(target)
    db.row_factory = sqlite3.Row
    yield db, manifest
    db.close()


def test_all_source_shots_and_match_boundaries_survive(imported):
    db, manifest = imported
    source = sqlite3.connect(f"file:{importer.SOURCE}?mode=ro", uri=True)
    expected = [(f"legacy_match_{int(mid)}", n) for mid, n in source.execute(
        "SELECT match_id,COUNT(*) FROM match_data GROUP BY match_id ORDER BY match_id")]
    actual = [tuple(r) for r in db.execute("SELECT match_name,COUNT(*) FROM shots GROUP BY match_name ORDER BY match_name")]
    source.close()
    assert actual == expected
    assert manifest["shots"] == sum(n for _, n in expected) == 5204
    assert not db.execute("PRAGMA foreign_key_check").fetchall()


def test_import_never_invents_metadata_videos_or_zone_mapping(imported):
    db, manifest = imported
    assert db.execute("SELECT COUNT(*) FROM matches WHERE tournament IS NOT NULL OR year IS NOT NULL OR round IS NOT NULL OR analyze_match_id IS NOT NULL").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM rallies WHERE has_video!=0 OR video_filename IS NOT NULL").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM shots WHERE hit_area IS NOT NULL OR landing_area IS NOT NULL").fetchone()[0] == 0
    assert manifest["player_mapping"] == {"Kento MOMOTA": "A", "CHOU Tien Chen": "B"}


def test_frozen_oracle_matches_both_original_and_imported_data(imported):
    db, _ = imported
    bank = json.loads((ROOT / "benchmarks/badminton_gpt/cases.json").read_text())
    assert bank["source_sha256"] == hashlib.sha256(importer.SOURCE.read_bytes()).hexdigest()
    source = sqlite3.connect(f"file:{importer.SOURCE}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for case in bank["cases"]:
        assert [dict(r) for r in source.execute(case["source_sql"])] == case["expected"], case["id"]
        assert [dict(r) for r in db.execute(case["target_sql"])] == case["expected"], case["id"]
    source.close()


def test_import_is_repeatable_and_does_not_modify_source(tmp_path):
    before = hashlib.sha256(importer.SOURCE.read_bytes()).hexdigest()
    target = tmp_path / "badminton.db"
    first = importer.build(target=target)
    second = importer.build(target=target)
    assert first["match_shots"] == second["match_shots"]
    assert before == hashlib.sha256(importer.SOURCE.read_bytes()).hexdigest()

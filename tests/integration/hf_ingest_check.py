"""Offline regression against the actual pinned parser in the DB Docker image.

docker run --rm --network none --read-only --tmpfs /tmp \
  -v "$PWD/scripts:/repo/scripts:ro" \
  -v "$PWD/tests/integration/hf_ingest_check.py:/check.py:ro" \
  badmintonai-db:7cccbb1 python3 /check.py
"""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, '/repo/scripts')
from huggingface_oracle import prepare
from import_huggingface_data import build


class HFImportCheck(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.snapshot = self.root / 'snapshot'
        self.output = self.root / 'output'
        self.files = []
        self.rows = [
            {'rally': 1, 'ball_round': 1, 'player': 'A', 'type': '殺球', 'frame_num': 10},
            {'rally': 1, 'ball_round': 2, 'player': 'B', 'type': '?', 'frame_num': 20},
            {'rally': 2, 'ball_round': 1, 'player': 'A', 'type': '挑球', 'frame_num': 30}]
        self.write('Data/2025game1.mp4/label/set1.csv', self.rows)
        self.write('Data/2025game1.mp4/label/set4.csv', self.rows[:1])
        self.write('Data/NYCU_Other_practice1.mp4/label/set1.csv', self.rows)
        self.write('Data/2025game1.mp4/match_info.csv', [dict(
            player_a='Player One', player_b='Player Two', tournament='Fixture',
            round='Final', year=2025, youtube_id='12345678901')])
        self.write('Data/2025game1.mp4/RallySeg.csv', [
            dict(Score='1_00_00', UpCourt='Player Two', DownCourt='Player One', Start=1, End=25),
            dict(Score='1_01_00', UpCourt='Player Two', DownCourt='Player One', Start=26, End=40)])
        (self.snapshot / 'Data/unknown.mp4').mkdir()
        inventory = self.files + [
            dict(type='file', path='Data/2025game1.mp4/rally_video/1_00_00.mp4', size=50_000_000),
            dict(type='file', path='Video/full_match.mp4', size=900_000_000)]
        (self.snapshot / 'inventory.json').write_text(json.dumps({'entries': inventory}))
        (self.snapshot / 'manifest.json').write_text(json.dumps(dict(
            repo_id='howard9199/Badminton', revision='a' * 40,
            csv_files=len(self.files), csv_bytes=sum(f['bytes'] for f in self.files), files=self.files)))

    def write(self, relative, rows):
        path = self.snapshot / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        blob = path.read_bytes()
        self.files.append(dict(path=relative, type='file', bytes=len(blob), size=len(blob),
                               sha256=hashlib.sha256(blob).hexdigest()))

    def test_original_parser_with_provenance_and_remote_metadata(self):
        prepare(self.snapshot, self.output)
        summary = build(self.snapshot, self.output)
        self.assertEqual((summary['matches'], summary['shots'], summary['rallies']), (3, 3, 2))
        self.assertEqual(summary['excluded_annotations'], 1)
        self.assertEqual(summary['videos_downloaded'], 0)
        with sqlite3.connect(self.output / 'badminton.db') as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM shot_sources').fetchone()[0], 3)
            self.assertEqual(db.execute('SELECT SUM(has_video),SUM(remote_video_available) FROM rallies').fetchone(), (0, 1))
            self.assertEqual(db.execute('SELECT player_a,player_b FROM matches WHERE name="2025game1"').fetchone(), ('Player One', 'Player Two'))
            self.assertEqual(db.execute('SELECT year,player_a FROM matches WHERE name="unknown"').fetchone(), (None, None))
            self.assertEqual(db.execute('SELECT type FROM shots WHERE player="B"').fetchone()[0], '未知球種')
            self.assertEqual(db.execute('SELECT raw_data FROM shot_sources WHERE shot_id=2').fetchone()[0], json.dumps(self.rows[1] | {'rally':'1', 'ball_round':'2', 'frame_num':'20'}, ensure_ascii=False))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM remote_match_videos').fetchone()[0], 1)
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertFalse([p for p in self.snapshot.rglob('*.mp4') if p.is_file()])

    def test_corrupt_cache_cannot_replace_completed_database(self):
        prepare(self.snapshot, self.output)
        build(self.snapshot, self.output)
        before = (self.output / 'badminton.db').read_bytes()
        (self.snapshot / self.files[0]['path']).write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            build(self.snapshot, self.output)
        self.assertEqual((self.output / 'badminton.db').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()

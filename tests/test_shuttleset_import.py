"""Source-level evidence for deduplication, preserved video links and atomic replacement."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import import_shuttleset_data as importer
import create_shuttleset_benchmark as oracle


@pytest.fixture(scope='module')
def dataset(tmp_path_factory):
    folder=tmp_path_factory.mktemp('shuttleset')
    target=folder/'badminton.db'
    with redirect_stdout(StringIO()):
        manifest=importer.build(target=target)
        bank=oracle.create(oracle=folder/'oracle.db',output=folder/'cases.json')
    db=sqlite3.connect(target)
    db.row_factory=sqlite3.Row
    source=sqlite3.connect(folder/'oracle.db')
    source.row_factory=sqlite3.Row
    yield db,source,manifest,bank,target
    db.close();source.close()


def test_independent_source_oracle_and_every_frozen_answer(dataset):
    db,source,manifest,bank,_=dataset
    frozen=json.loads((ROOT/'benchmarks/badminton_gpt/shuttleset_cases.json').read_text())
    assert bank==frozen
    for case in bank['cases']:
        expected=[dict(r) for r in source.execute(case['source_sql'])]
        assert expected==case['expected'],case['id']
        assert [dict(r) for r in db.execute(case['target_sql'])]==expected,case['id']
    assert (manifest['matches'],manifest['shots'],manifest['rallies'])==(94,81938,7888)
    assert manifest['source_shot_rows']==88840
    assert manifest['duplicate_annotations_removed']==6902
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_exact_duplicate_removed_but_every_source_row_retained(dataset):
    db,_,_,_,_=dataset
    name='Kento_MOMOTA_CHOU_Tien_Chen_Fuzhou_Open_2018_Finals'
    ids=db.execute('SELECT shot_id FROM shots WHERE match_name=? AND set_no=3 AND rally=10 AND ball_round=29',(name,)).fetchall()
    assert len(ids)==1
    records=db.execute('SELECT source_row,raw_data FROM shot_sources WHERE shot_id=?',(ids[0][0],)).fetchall()
    assert len(records)==2
    assert json.loads(records[0]['raw_data'])==json.loads(records[1]['raw_data'])
    assert records[0]['source_row']!=records[1]['source_row']
    assert db.execute('SELECT COUNT(DISTINCT shot_id) FROM shot_sources').fetchone()[0]==81938
    assert db.execute('SELECT COUNT(*) FROM match_sources').fetchone()[0]==102


def test_same_shot_number_different_frames_is_not_lost(dataset):
    db,_,_,_,_=dataset
    name='Anthony_Sinisuka_Ginting_Rasmus_Gemke_YONEX_Thailand_Open_2021_QuarterFinals'
    rows=db.execute('SELECT d.frame_num,d.flaw FROM shots s JOIN shot_details d USING(shot_id) WHERE s.match_name=? AND s.set_no=3 AND s.rally=25 AND s.ball_round=1 ORDER BY d.frame_num',(name,)).fetchall()
    assert [tuple(r) for r in rows]==[(128176,1),(129140,1)]
    issue=db.execute("SELECT details FROM data_quality_issues WHERE code='repeated_shot_number'").fetchone()
    assert len(json.loads(issue[0])['shot_ids'])==2


def test_links_are_sources_and_never_claimed_as_local_video(dataset):
    db,_,_,_,_=dataset
    assert db.execute('SELECT COUNT(*) FROM matches WHERE video_url IS NOT NULL').fetchone()[0]==43
    assert db.execute("SELECT COUNT(*) FROM match_links WHERE availability='unverified'").fetchone()[0]==43
    assert db.execute('SELECT COUNT(*) FROM rallies WHERE has_video<>0 OR video_filename IS NOT NULL').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM matches WHERE analyze_match_id IS NOT NULL').fetchone()[0]==0
    url=db.execute('SELECT video_url FROM matches WHERE name=?',(oracle.CHART_MATCH,)).fetchone()[0]
    assert url=='https://www.youtube.com/watch?v=O669aZhH0LI'


def test_original_fields_preserved_without_false_grid_mapping(dataset):
    db,_,_,_,_=dataset
    assert db.execute('SELECT COUNT(*) FROM shot_details').fetchone()[0]==81938
    assert db.execute('SELECT COUNT(*) FROM shots WHERE hit_area IS NOT NULL OR landing_area IS NOT NULL').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM shot_details WHERE source_landing_area IS NOT NULL').fetchone()[0]>70000
    assert db.execute('SELECT COUNT(*) FROM match_homographies').fetchone()[0]==102
    assert db.execute('SELECT COUNT(*) FROM matches WHERE match_date IS NULL OR tournament IS NULL OR year IS NULL').fetchone()[0]==0
    # A/B means winner/loser per match, rather than a single pair of fixed names.
    assert db.execute('SELECT COUNT(DISTINCT player_a) FROM matches').fetchone()[0]>10
    assert db.execute('SELECT COUNT(*) FROM shots WHERE shot_id IS NULL').fetchone()[0]==0


def test_legacy_subset_preserved_and_resolved_without_double_counting(dataset):
    db,_,_,_,_=dataset
    old=sqlite3.connect(importer.SOURCE)
    assert [tuple(r) for r in db.execute('SELECT match_name,COUNT(*) FROM legacy_shots GROUP BY match_name ORDER BY match_name')]==[(f'legacy_match_{int(mid)}',n) for mid,n in old.execute('SELECT match_id,COUNT(*) FROM match_data GROUP BY match_id ORDER BY match_id')]
    old.close()
    assert db.execute('SELECT COUNT(*) FROM legacy_shots').fetchone()[0]==5204
    aliases=db.execute('SELECT * FROM legacy_match_aliases').fetchall()
    assert len(aliases)==5
    assert all(r['matched_frame_player_keys']==r['total_frame_player_keys'] for r in aliases)
    assert db.execute("SELECT match_name FROM legacy_match_aliases WHERE legacy_name='legacy_match_1'").fetchone()[0]==oracle.CHART_MATCH
    assert not db.execute("SELECT 1 FROM matches WHERE name LIKE 'legacy_match_%'").fetchall()


def test_repeat_build_does_not_change_sources_or_counts(dataset):
    db,_,_,_,target=dataset
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for _,p in importer.ARCHIVES}
    with redirect_stdout(StringIO()):
        manifest=importer.build(target=target)
    fresh=sqlite3.connect(target)
    assert fresh.execute('SELECT COUNT(*) FROM shots').fetchone()[0]==81938
    assert fresh.execute('SELECT COUNT(*) FROM shot_sources').fetchone()[0]==88840
    assert manifest['quality_issues']==1
    fresh.close()
    assert before=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before}


def test_failed_second_archive_preserves_existing_database(dataset,tmp_path):
    *_,target=dataset
    before=hashlib.sha256(target.read_bytes()).hexdigest()
    broken=tmp_path/'broken.zip'
    with zipfile.ZipFile(broken,'w') as archive:
        archive.writestr('README.md','No dataset here')
    with pytest.raises(KeyError),redirect_stdout(StringIO()):
        importer.build(archives=[importer.ARCHIVES[0],('ShuttleSet22',broken)],target=target)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==before


def test_identity_uses_event_date_and_normalizes_numeric_representation():
    assert importer.number('2022.0',integer=True)==2022
    with pytest.raises(ValueError):importer.number('1.5',integer=True)
    a={'year':'2022.0','month':'1','day':'1','winner':'AN Se Young','loser':'Akane YAMAGUCHI','tournament':'Example Open','round':'Finals'}
    b={**a,'winner':'An Seyoung','day':'2'}
    assert importer.identity(a)!=importer.identity(b)
    assert importer.identity(a)==importer.identity({**b,'day':'1'})

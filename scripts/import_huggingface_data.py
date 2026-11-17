#!/usr/bin/env python3
"""Offline HF builder using the pinned upstream parser; run inside the DB image."""
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from types import SimpleNamespace
import urllib.parse


def build(snapshot,output,upstream_root='/app'):
    sys.path.insert(0,str(upstream_root))
    import ingest as upstream
    from ingest_lib.parse import extract_tournament_round
    snapshot,output=Path(snapshot),Path(output)
    source_manifest=json.loads((snapshot/'manifest.json').read_text())
    revision=source_manifest['revision'];repo=source_manifest['repo_id']
    if not re.fullmatch(r'[a-f0-9]{40}',revision):raise ValueError('Invalid pinned HF revision')
    if repo!='howard9199/Badminton':raise ValueError('Unexpected dataset')
    for f in source_manifest['files']:
        if hashlib.sha256((snapshot/f['path']).read_bytes()).hexdigest()!=f['sha256']:
            raise ValueError('Cached CSV integrity failed: '+f['path'])
    bank=json.loads((output/'hf_cases.json').read_text())
    if bank['revision']!=revision:raise ValueError('Oracle revision differs from source')
    src=upstream.LocalSource(snapshot/'Data')
    best={};variants=defaultdict(list)
    for folder in src.folders():
        key=upstream.norm_name(folder);variants[key].append(folder)
        if key not in best or src.label_count(folder)>src.label_count(best[key]):best[key]=folder
    aliases={f:best[k].removesuffix('.mp4') for k,items in variants.items() for f in items}
    target=output/'candidate.db';target.unlink(missing_ok=True)
    db=sqlite3.connect(target)
    try:
        db.executescript(upstream.DDL)
        db.execute('CREATE UNIQUE INDEX idx_matches_name ON matches(name)')
        db.execute('PRAGMA foreign_keys=ON')
        db.executescript('''
        ALTER TABLE matches ADD COLUMN video_url TEXT;
        ALTER TABLE shots ADD COLUMN shot_id INTEGER;
        CREATE UNIQUE INDEX idx_hf_shot_id ON shots(shot_id);
        ALTER TABLE rallies ADD COLUMN remote_video_available INTEGER NOT NULL DEFAULT 0;
        CREATE TABLE hf_dataset(repo_id TEXT,revision TEXT,csv_files INTEGER,csv_bytes INTEGER);
        CREATE TABLE hf_source_files(path TEXT PRIMARY KEY,sha256 TEXT,bytes INTEGER);
        CREATE TABLE match_sources(match_name TEXT PRIMARY KEY REFERENCES matches(name),selected_folder TEXT,folder_variants TEXT,ab_source TEXT,raw_match_info TEXT);
        CREATE TABLE shot_sources(shot_id INTEGER PRIMARY KEY REFERENCES shots(shot_id),source_path TEXT,source_row INTEGER,frame_num INTEGER,end_frame_num INTEGER,raw_data TEXT NOT NULL);
        CREATE TABLE rally_sources(match_name TEXT REFERENCES matches(name),source_row INTEGER,raw_data TEXT);
        CREATE TABLE rejected_annotations(match_name TEXT,source_path TEXT,source_row INTEGER,error TEXT,raw_data TEXT);
        CREATE TABLE excluded_annotations(match_name TEXT,source_path TEXT,source_row INTEGER,reason TEXT,raw_data TEXT);
        CREATE TABLE data_quality_issues(match_name TEXT,code TEXT,details TEXT);
        CREATE TABLE remote_videos(match_name TEXT REFERENCES matches(name),rally_id TEXT,repo_path TEXT PRIMARY KEY,bytes INTEGER,remote_url TEXT,availability TEXT DEFAULT 'listed',local_downloaded INTEGER DEFAULT 0);
        CREATE INDEX idx_remote_rally ON remote_videos(match_name,rally_id);
        CREATE TABLE remote_match_videos(repo_path TEXT PRIMARY KEY,bytes INTEGER,remote_url TEXT,availability TEXT DEFAULT 'listed',local_downloaded INTEGER DEFAULT 0);
        ''')
        db.execute('INSERT INTO hf_dataset VALUES (?,?,?,?)',(repo,revision,source_manifest['csv_files'],source_manifest['csv_bytes']))
        db.executemany('INSERT INTO hf_source_files VALUES (?,?,?)',[(f['path'],f['sha256'],f['bytes']) for f in source_manifest['files']])
        stats=Counter()
        loader=SimpleNamespace(_extract_tournament_round=extract_tournament_round)
        for folder in sorted(best.values()):
            name=folder.removesuffix('.mp4');practice=name.startswith('NYCU_Other_practice')
            info=upstream.match_info(src,folder)
            segments=[]
            segment_path=src.csv_path(folder,'RallySeg.csv')
            if segment_path and not practice:segments=upstream.parse_rally_seg(segment_path)
            pa,pb=upstream.derive_ab(folder,segments) if segments else (None,None)
            upstream.insert_match_row(db.cursor(),folder,loader,pa,pb,'hf',None,info)
            # Unlike the original fallback, an unlabelled practice folder is not assumed to be from 2022.
            year_match=re.search(r'(20\d{2})',name)
            year=int(float(info['year'])) if info and info.get('year') else (int(year_match[1]) if year_match else None)
            video_id=info.get('youtube_id','').strip() if info else ''
            video_url='https://www.youtube.com/watch?v='+video_id if re.fullmatch(r'[A-Za-z0-9_-]{11}',video_id) else None
            db.execute('UPDATE matches SET year=?,video_url=? WHERE name=?',(year,video_url,name))
            method='match_info' if info else ('upstream_folder_order_and_RallySeg' if pa and pb else 'unknown')
            db.execute('INSERT INTO match_sources VALUES (?,?,?,?,?)',(name,folder,json.dumps(variants[upstream.norm_name(folder)]),method,json.dumps(info,ensure_ascii=False) if info else None))
            if practice:continue
            for extra in sorted((snapshot/'Data'/folder/'label').glob('set*.csv')):
                if extra.name in {'set1.csv','set2.csv','set3.csv'}:continue
                relative=extra.relative_to(snapshot).as_posix()
                with extra.open(encoding='utf-8-sig',newline='') as file:
                    for row_no,raw in enumerate(csv.DictReader(file),2):
                        db.execute('INSERT INTO excluded_annotations VALUES (?,?,?,?,?)',(name,relative,row_no,'unsupported_set_number',json.dumps(raw,ensure_ascii=False)))
                db.execute('INSERT INTO data_quality_issues VALUES (?,?,?)',(name,'unsupported_set_number',relative+' retained separately; original importer supports sets 1-3'))
            before=db.execute('SELECT COALESCE(MAX(rowid),0) FROM shots').fetchone()[0]
            if segments or src.label_count(folder):
                result=upstream.ingest_match(db.cursor(),folder,src,videos=set())
                stats['upstream_skipped_rows']+=result['skipped'];stats['normalized_mojibake_rows']+=result['mojibake']
            after=db.execute('SELECT COALESCE(MAX(rowid),0) FROM shots').fetchone()[0]
            db.execute('UPDATE shots SET shot_id=rowid WHERE rowid>? AND rowid<=?',(before,after))
            rowids=iter(range(before+1,after+1));accepted=0
            for sn in (1,2,3):
                path=src.csv_path(folder,f'label/set{sn}.csv')
                if not path:continue
                relative=f'Data/{folder}/label/set{sn}.csv'
                with path.open(encoding='utf-8-sig',newline='') as file:
                    for row_no,raw in enumerate(csv.DictReader(file),2):
                        try:label=upstream.ShotLabel.model_validate(raw.copy())
                        except Exception as exc:
                            db.execute('INSERT INTO rejected_annotations VALUES (?,?,?,?,?)',(name,relative,row_no,type(exc).__name__,json.dumps(raw,ensure_ascii=False)))
                            continue
                        shot_id=next(rowids);accepted+=1
                        db.execute('INSERT INTO shot_sources VALUES (?,?,?,?,?,?)',(shot_id,relative,row_no,label.frame_num,label.end_frame_num,json.dumps(raw,ensure_ascii=False)))
            if accepted!=after-before:raise ValueError('Raw lineage differs from upstream parser: '+folder)
            if segment_path:
                with segment_path.open(encoding='utf-8-sig',newline='') as file:
                    for row_no,raw in enumerate(csv.DictReader(file),2):
                        db.execute('INSERT INTO rally_sources VALUES (?,?,?)',(name,row_no,json.dumps(raw,ensure_ascii=False)))
            if not info and not (pa and pb):
                db.execute('INSERT INTO data_quality_issues VALUES (?,?,?)',(name,'unknown_player_mapping','No authoritative match_info or usable RallySeg names; player names remain NULL'))
        inventory=json.loads((snapshot/'inventory.json').read_text())
        for entry in inventory['entries']:
            parts=entry['path'].split('/')
            if entry.get('type')=='file' and len(parts)==2 and parts[0]=='Video' and parts[1].endswith('.mp4'):
                url=f'https://huggingface.co/datasets/{repo}/resolve/{revision}/'+urllib.parse.quote(entry['path'],safe='/')
                db.execute('INSERT INTO remote_match_videos(repo_path,bytes,remote_url) VALUES (?,?,?)',(entry['path'],entry['size'],url))
            if entry.get('type')!='file' or len(parts)!=4 or parts[0]!='Data' or parts[1] not in aliases or parts[2]!='rally_video' or not parts[3].endswith('.mp4'):continue
            url=f'https://huggingface.co/datasets/{repo}/resolve/{revision}/'+urllib.parse.quote(entry['path'],safe='/')
            db.execute('INSERT INTO remote_videos(match_name,rally_id,repo_path,bytes,remote_url) VALUES (?,?,?,?,?)',(aliases[parts[1]],Path(parts[3]).stem,entry['path'],entry['size'],url))
        db.execute('UPDATE rallies SET remote_video_available=EXISTS(SELECT 1 FROM remote_videos v WHERE v.match_name=rallies.match_name AND v.rally_id=rallies.rally_id)')
        db.execute('CREATE INDEX idx_hf_shots_rally ON shots(match_name,set_no,rally)')
        db.commit();db.row_factory=sqlite3.Row
        checks=[]
        for case in bank['cases']:
            actual=[dict(r) for r in db.execute(case['target_sql'])]
            if actual!=case['expected']:raise ValueError('Independent CSV oracle failed: '+case['id'])
            checks.append(case['id'])
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Foreign key check failed')
        summary={'dataset':'huggingface','repo_id':repo,'revision':revision,'csv_files':source_manifest['csv_files'],'csv_bytes':source_manifest['csv_bytes'],
                 **{t:db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ['matches','shots','rallies','remote_videos','remote_match_videos','excluded_annotations']},
                 'official_matches':db.execute('SELECT COUNT(*) FROM matches WHERE is_practice=0').fetchone()[0],
                 'practice_catalog':db.execute('SELECT COUNT(*) FROM matches WHERE is_practice=1').fetchone()[0],
                 'labeled_matches':db.execute('SELECT COUNT(DISTINCT match_name) FROM shots').fetchone()[0],
                 'remote_rallies':db.execute('SELECT COUNT(*) FROM rallies WHERE remote_video_available=1').fetchone()[0],
                 'videos_downloaded':0,'video_links':db.execute('SELECT COUNT(*) FROM matches WHERE video_url IS NOT NULL').fetchone()[0],
                 'unknown_player_mappings':db.execute("SELECT COUNT(*) FROM match_sources WHERE ab_source='unknown'").fetchone()[0],
                 'parser_stats':dict(stats),'independent_cases_passed':checks,'upstream_parser':'pinned mcps/badminton-db/ingest.py',
                 'limitations':['practice catalog retained but practice annotations excluded, matching upstream defaults',
                    'A/B comes from match_info or upstream folder/RallySeg convention, not a universal winner/loser rule',
                    'remote video inventory is retained; local has_video=0 because no MP4 was downloaded',
                    'unknown metadata stays NULL; no advanced analysis credentials or model call used']}
    finally:
        db.close()
    target.replace(output/'badminton.db')
    (output/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))
    return summary


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',default='/snapshot');parser.add_argument('--output',default='/output')
    args=parser.parse_args()
    build(args.snapshot,args.output)

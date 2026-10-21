#!/usr/bin/env python3
"""Build a deduplicated, provenance-preserving ShuttleSet database from local ZIPs."""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import ExitStack, closing, redirect_stdout
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import zipfile

from import_badminton_gpt_data import ROOT, SOURCE, TARGET, build as build_legacy, upstream_schema

ARCHIVES = [(name, ROOT / 'data/sources' / (name + '.zip')) for name in ('ShuttleSet', 'ShuttleSet22')]
EXTENSIONS = '''
ALTER TABLE matches ADD COLUMN match_date TEXT;
ALTER TABLE matches ADD COLUMN video_url TEXT;
ALTER TABLE shots ADD COLUMN shot_id INTEGER;
CREATE UNIQUE INDEX idx_shot_id ON shots(shot_id);
CREATE TABLE datasets(name TEXT PRIMARY KEY, archive_path TEXT, sha256 TEXT, match_rows INTEGER, shot_rows INTEGER);
CREATE TABLE match_sources(dataset TEXT REFERENCES datasets(name), source_id TEXT,
 match_name TEXT REFERENCES matches(name), raw_metadata TEXT NOT NULL,
 PRIMARY KEY(dataset,source_id));
CREATE TABLE match_homographies(dataset TEXT REFERENCES datasets(name), match_name TEXT REFERENCES matches(name),
 raw_data TEXT NOT NULL, PRIMARY KEY(dataset,match_name));
CREATE TABLE match_links(match_name TEXT REFERENCES matches(name), url TEXT, dataset TEXT REFERENCES datasets(name),
 availability TEXT NOT NULL DEFAULT 'unverified', PRIMARY KEY(match_name,url));
CREATE TABLE shot_details(shot_id INTEGER PRIMARY KEY REFERENCES shots(shot_id), frame_num INTEGER,
 timestamp_seconds REAL, source_hit_area INTEGER, source_landing_area INTEGER,
 hit_x REAL,hit_y REAL,landing_x REAL,landing_y REAL,
 player_location_x REAL,player_location_y REAL,opponent_location_x REAL,opponent_location_y REAL,
 flaw INTEGER, annotation_fingerprint TEXT UNIQUE NOT NULL);
CREATE TABLE shot_sources(shot_id INTEGER REFERENCES shots(shot_id), dataset TEXT REFERENCES datasets(name),
 source_path TEXT, source_row INTEGER, raw_data TEXT NOT NULL,
 PRIMARY KEY(dataset,source_path,source_row));
CREATE INDEX idx_shot_sources_id ON shot_sources(shot_id);
CREATE TABLE data_quality_issues(code TEXT,match_name TEXT,dataset TEXT,details TEXT NOT NULL);
CREATE TABLE legacy_match_aliases(legacy_name TEXT PRIMARY KEY REFERENCES legacy_matches(name),
 match_name TEXT REFERENCES matches(name),matched_frame_player_keys INTEGER,total_frame_player_keys INTEGER,
 evidence TEXT NOT NULL);
'''


def number(value, *, integer=False):
    if value is None or str(value).strip() == '':
        return None
    result = Decimal(str(value).strip())
    if not result.is_finite() or (integer and result != result.to_integral_value()):
        raise ValueError(f'Invalid numeric annotation: {value!r}')
    return int(result) if integer else float(result)


def normalized(value):
    value = str(value or '').strip()
    if not value:
        return None
    try:
        n = Decimal(value)
        if n.is_finite():
            return format(n.normalize(), 'f')
    except InvalidOperation:
        pass
    return value


def person(value):
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def identity(meta):
    when = date(*(number(meta[k], integer=True) for k in ('year', 'month', 'day'))).isoformat()
    players = tuple(sorted(person(meta[k]) for k in ('winner', 'loser')))
    if not all(players) or players[0] == players[1]:
        raise ValueError('Missing or ambiguous match players')
    # A pair can meet again: the date, event and round all participate in identity.
    event = re.sub(r'[^a-z0-9]', '', meta['tournament'].casefold())
    stage = re.sub(r'[^a-z0-9]', '', meta['round'].casefold())
    return when, players, event, stage


def timestamp(value):
    if not value:
        return None
    h, m, s = (float(part) for part in value.split(':'))
    return h * 3600 + m * 60 + s


def read_archive(path):
    """Read data only; never extract paths or run bundled Python programs."""
    with zipfile.ZipFile(path) as archive:
        def rows(name):
            return list(csv.DictReader(StringIO(archive.read(name).decode('utf-8-sig'))))
        matches = rows('set/match.csv')
        homographies = rows('set/homography.csv')
        sets = {name: rows(name) for name in sorted(archive.namelist())
                if re.fullmatch(r'set/[^/]+/set[123]\.csv', name)}
    folders = {m['video'] for m in matches}
    if {Path(p).parent.name for p in sets} != folders:
        raise ValueError('Match catalog does not cover exactly the annotation folders')
    return matches, homographies, sets


def build(archives=ARCHIVES, target=TARGET, legacy_source=SOURCE):
    archives = [(name, Path(path)) for name, path in archives]
    target = Path(target)
    for _, path in archives:
        if not path.is_file():
            raise FileNotFoundError(f'Missing source archive: {path}')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shuttleset-', dir=target.parent) as temporary, ExitStack() as stack:
        temp = Path(temporary) / 'badminton.db'
        with redirect_stdout(StringIO()):
            build_legacy(source=legacy_source, target=temp)
        db = stack.enter_context(closing(sqlite3.connect(temp)))
        db.execute('PRAGMA foreign_keys=ON')
        for table in ('matches', 'shots', 'rallies'):
            db.execute(f'ALTER TABLE {table} RENAME TO legacy_{table}')
        db.execute('CREATE UNIQUE INDEX idx_legacy_matches_name ON legacy_matches(name)')
        for index in ('idx_matches_name','idx_shots_match_type','idx_shots_match_player','idx_rallies_match_video'):
            db.execute(f'DROP INDEX {index}')
        db.executescript(upstream_schema())
        db.execute('CREATE UNIQUE INDEX idx_matches_name ON matches(name)')
        db.executescript(EXTENSIONS)
        by_identity, folder_identity, fingerprints = {}, {}, {}
        natural_keys = defaultdict(set)
        frame_keys = defaultdict(set)
        counts = Counter()
        sources = []
        overlaps = []
        canonical_meta = {}
        for dataset, path in archives:
            matches, homographies, sets = read_archive(path)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            shot_rows = sum(len(v) for v in sets.values())
            source_path = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
            db.execute('INSERT INTO datasets VALUES (?,?,?,?,?)', (dataset, source_path, checksum, len(matches), shot_rows))
            sources.append({'dataset':dataset,'archive':source_path,'sha256':checksum,'match_rows':len(matches),'shot_rows':shot_rows})
            source_names = {}
            for meta in sorted(matches, key=lambda m: number(m['id'], integer=True)):
                key = identity(meta)
                folder = meta['video']
                if folder in folder_identity and folder_identity[folder] != key:
                    raise ValueError('Folder name reused for a different match: ' + folder)
                folder_identity[folder] = key
                name = by_identity.get(key)
                if name is None:
                    name = folder
                    by_identity[key] = name
                    canonical_meta[name] = meta
                    url = meta.get('url', '').strip() or None
                    db.execute('INSERT INTO matches(folder,name,tournament,round,player_a,player_b,year,source,match_date,video_url) VALUES (?,?,?,?,?,?,?,?,?,?)',
                               (folder,name,meta['tournament'],meta['round'],meta['winner'],meta['loser'],number(meta['year'],integer=True),dataset,key[0],url))
                else:
                    previous = canonical_meta[name]
                    if person(previous['winner']) != person(meta['winner']) or number(previous['set'],integer=True) != number(meta['set'],integer=True):
                        raise ValueError('Overlapping match metadata conflicts: ' + name)
                    overlaps.append({'match_name':name,'additional_dataset':dataset})
                source_names[folder] = name
                db.execute('INSERT INTO match_sources VALUES (?,?,?,?)', (dataset,str(number(meta['id'],integer=True)),name,json.dumps(meta,ensure_ascii=False)))
                url = meta.get('url', '').strip()
                if url:
                    if not url.startswith('https://www.youtube.com/watch?v='):
                        raise ValueError('Unexpected video URL: ' + name)
                    existing = db.execute('SELECT video_url FROM matches WHERE name=?',(name,)).fetchone()[0]
                    if existing and existing != url:
                        raise ValueError('Conflicting video URLs: ' + name)
                    db.execute('UPDATE matches SET video_url=? WHERE name=?',(url,name))
                    db.execute('INSERT OR IGNORE INTO match_links(match_name,url,dataset) VALUES (?,?,?)',(name,url,dataset))
            for h in homographies:
                if h['video'] not in source_names:
                    raise ValueError('Unknown homography match')
                db.execute('INSERT INTO match_homographies VALUES (?,?,?)',(dataset,source_names[h['video']],json.dumps(h,ensure_ascii=False)))
            for source_path, rows in sets.items():
                name = source_names[Path(source_path).parent.name]
                set_no = int(Path(source_path).stem[3:])
                for row_no, row in enumerate(rows, start=2):
                    payload = {k:normalized(v) for k,v in row.items()}
                    payload['time'] = timestamp(row.get('time'))
                    fingerprint = hashlib.sha256(json.dumps([name,set_no,payload],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    shot_id = fingerprints.get(fingerprint)
                    if shot_id is None:
                        shot_id = len(fingerprints) + 1
                        fingerprints[fingerprint] = shot_id
                        if row['player'] not in {'A','B'} or row.get('getpoint_player','') not in {'','A','B'}:
                            raise ValueError('Invalid player label')
                        rally = number(row['rally'],integer=True)
                        ball = number(row['ball_round'],integer=True)
                        frame = number(row['frame_num'],integer=True)
                        if rally is None or ball is None or frame is None:
                            raise ValueError('Missing shot identity')
                        # Raw court codes are retained separately, without assuming the upstream grid.
                        db.execute('INSERT INTO shots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (name,set_no,rally,ball,row['player'],normalized(row['server']),row['type'],
                             number(row['aroundhead'],integer=True),number(row['backhand'],integer=True),None,None,
                             row['lose_reason'] or None,row['win_reason'] or None,row['getpoint_player'] or None,
                             number(row['roundscore_A'],integer=True),number(row['roundscore_B'],integer=True),shot_id))
                        details=[shot_id,frame,timestamp(row.get('time')),number(row['hit_area'],integer=True),number(row['landing_area'],integer=True)]
                        details += [number(row.get(k)) for k in ('hit_x','hit_y','landing_x','landing_y','player_location_x','player_location_y','opponent_location_x','opponent_location_y')]
                        details += [number(row.get('flaw'),integer=True),fingerprint]
                        db.execute('INSERT INTO shot_details VALUES ('+','.join('?' for _ in details)+')',details)
                        natural_keys[(name,set_no,rally,ball)].add(shot_id)
                        frame_keys[name].add((set_no,frame,row['player']))
                    else:
                        counts['duplicate_annotations_removed'] += 1
                    db.execute('INSERT INTO shot_sources VALUES (?,?,?,?,?)',(shot_id,dataset,source_path,row_no,json.dumps(row,ensure_ascii=False)))
        for key, ids in natural_keys.items():
            if len(ids)>1:
                db.execute('INSERT INTO data_quality_issues VALUES (?,?,?,?)',('repeated_shot_number',key[0],None,json.dumps({'set_no':key[1],'rally':key[2],'ball_round':key[3],'shot_ids':sorted(ids),'resolution':'preserved distinct annotations; do not count ball_round as a unique key'})))
        db.execute('''INSERT INTO rallies SELECT s.match_name,
          CAST(s.set_no AS TEXT)||'_source_'||CAST(s.rally AS TEXT),s.set_no,
          (SELECT first.roundscore_a FROM shots first JOIN shot_details fd USING(shot_id)
            WHERE first.match_name=s.match_name AND first.set_no=s.set_no AND first.rally=s.rally ORDER BY fd.frame_num,first.shot_id LIMIT 1),
          (SELECT first.roundscore_b FROM shots first JOIN shot_details fd USING(shot_id)
            WHERE first.match_name=s.match_name AND first.set_no=s.set_no AND first.rally=s.rally ORDER BY fd.frame_num,first.shot_id LIMIT 1),
          MIN(d.frame_num),MAX(d.frame_num),0,NULL
          FROM shots s JOIN shot_details d USING(shot_id) GROUP BY s.match_name,s.set_no,s.rally''')
        # Resolve the old transformed subset using every distinct (set, frame, player) key.
        src = stack.enter_context(closing(sqlite3.connect(f'file:{legacy_source}?mode=ro',uri=True)))
        src.row_factory=sqlite3.Row
        aliases=[]
        for mid, in src.execute('SELECT DISTINCT match_id FROM match_data ORDER BY match_id'):
            old=list(src.execute('SELECT * FROM match_data WHERE match_id=?',(mid,)))
            candidates=[]
            for name, meta in canonical_meta.items():
                ab={person(meta['winner']):'A',person(meta['loser']):'B'}
                if any(person(r['player']) not in ab for r in old):
                    continue
                keys={(int(r['set']),int(r['frame_num']),ab[person(r['player'])]) for r in old}
                if keys and keys <= frame_keys[name]:
                    candidates.append((name,len(keys)))
            if len(candidates)!=1:
                raise ValueError(f'Legacy record {mid} has no unique complete frame/player match')
            name,n=candidates[0]
            alias=f'legacy_match_{int(mid)}'
            evidence='100% of distinct (set,frame,player) keys match exactly one source match; active queries use the original full annotation'
            db.execute('INSERT INTO legacy_match_aliases VALUES (?,?,?,?,?)',(alias,name,n,n,evidence))
            aliases.append({'legacy_name':alias,'match_name':name,'matched_keys':n,'total_keys':n})
        src.close()
        db.execute('CREATE INDEX idx_shots_rally ON shots(match_name,set_no,rally)')
        db.execute('CREATE INDEX idx_matches_date ON matches(match_date)')
        db.commit()
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        manifest={'dataset':'shuttleset_merged','created_at':datetime.now(timezone.utc).isoformat(),
          'upstream_revision':'7cccbb18aba8bcfa096f22b923fb2aa16326e6ed','sources':sources,
          **{table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('matches','shots','rallies')},
          'source_shot_rows':sum(s['shot_rows'] for s in sources),
          'duplicate_annotations_removed':counts['duplicate_annotations_removed'],
          'overlapping_matches':overlaps,'legacy_aliases':aliases,
          'video_links':db.execute('SELECT COUNT(*) FROM match_links').fetchone()[0],
          'quality_issues':db.execute('SELECT COUNT(*) FROM data_quality_issues').fetchone()[0],
          'limitations':['video URLs unverified; no local video files or playable rally clips',
            'raw source court codes preserved; upstream hit_area/landing_area remain NULL',
            'timestamps and frames are annotations, not verified clip boundaries',
            'one repeated shot number is retained with a quality flag',
            'old processed subset retained in legacy_* tables, excluded from active totals']}
        db.close()
        temp.replace(target)
        target.with_name('manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
    return manifest


if __name__=='__main__':
    build()

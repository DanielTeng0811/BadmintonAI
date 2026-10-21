#!/usr/bin/env python3
"""Independent CSV oracle for the merged dataset; does not import the production importer."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ORACLE=ROOT/'.runtime/badminton-gpt/data/shuttleset-oracle.db'
OUTPUT=ROOT/'benchmarks/badminton_gpt/shuttleset_cases.json'
CHART_MATCH='Kento_MOMOTA_CHOU_Tien_Chen_Fuzhou_Open_2019_Finals'


def logical_digest(db):
    digest=hashlib.sha256()
    for table in ('source_matches','source_shots'):
        digest.update(table.encode())
        for row in db.execute(f'SELECT * FROM {table} ORDER BY rowid'):
            digest.update((json.dumps(list(row),ensure_ascii=False,separators=(',',':'))+'\n').encode())
    return digest.hexdigest()


def create(archives=None, oracle=ORACLE, output=OUTPUT, *, refresh=False):
    archives=archives or [(n,ROOT/'data/sources'/f'{n}.zip') for n in ('ShuttleSet','ShuttleSet22')]
    oracle,output=Path(oracle),Path(output)
    if output.exists() and not refresh:
        raise ValueError('Frozen oracle already exists; use --refresh only after reviewing source changes')
    oracle.parent.mkdir(parents=True,exist_ok=True)
    temporary=oracle.with_suffix('.building.db')
    temporary.unlink(missing_ok=True)
    db=sqlite3.connect(temporary)
    db.executescript('''
      CREATE TABLE source_matches(dataset TEXT,name TEXT,year INTEGER,month INTEGER,day INTEGER,tournament TEXT,round TEXT,player_a TEXT,player_b TEXT,url TEXT);
      CREATE TABLE source_shots(dataset TEXT,match_name TEXT,set_no INTEGER,rally INTEGER,ball_round INTEGER,frame_num INTEGER,player TEXT,type TEXT,win_reason TEXT,lose_reason TEXT,getpoint_player TEXT,roundscore_a INTEGER,roundscore_b INTEGER,flaw INTEGER,fingerprint TEXT);
      CREATE VIEW catalog AS SELECT name,MIN(year) year,MIN(player_a) player_a,MIN(player_b) player_b,MAX(url) video_url FROM source_matches GROUP BY name;
      CREATE VIEW annotations AS SELECT * FROM source_shots WHERE rowid IN (SELECT MIN(rowid) FROM source_shots GROUP BY fingerprint);
    ''')
    sources=[]
    for dataset,path in archives:
        path=Path(path)
        sources.append({'dataset':dataset,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        with zipfile.ZipFile(path) as archive:
            def read(name):
                return csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig')))
            for m in read('set/match.csv'):
                db.execute('INSERT INTO source_matches VALUES (?,?,?,?,?,?,?,?,?,?)',(dataset,m['video'],int(float(m['year'])),int(float(m['month'])),int(float(m['day'])),m['tournament'],m['round'],m['winner'],m['loser'],m.get('url') or None))
            for name in sorted(archive.namelist()):
                if not re.fullmatch(r'set/[^/]+/set[123]\.csv',name):continue
                match=Path(name).parent.name; sn=int(Path(name).stem[3:])
                for r in read(name):
                    # Independent implementation: exact numeric values via JSON strings,
                    # ignoring representation-only changes such as '1' versus '1.0'.
                    canonical={}
                    for k,v in r.items():
                        v=v.strip()
                        if not v:canonical[k]=None;continue
                        try:canonical[k]=format(float(v),'.15g')
                        except ValueError:canonical[k]=v
                    h,m,s=map(float,r['time'].split(':'))
                    canonical['time']=h*3600+m*60+s
                    fingerprint=hashlib.sha256(json.dumps([match,sn,canonical],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                    def num(k):return int(float(r[k])) if r[k] else None
                    db.execute('INSERT INTO source_shots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(dataset,match,sn,num('rally'),num('ball_round'),num('frame_num'),r['player'],r['type'],r['win_reason'] or None,r['lose_reason'] or None,r['getpoint_player'] or None,num('roundscore_A'),num('roundscore_B'),num('flaw'),fingerprint))
    db.execute('CREATE INDEX idx_oracle_fingerprint ON source_shots(fingerprint)')
    db.commit()
    db.row_factory=sqlite3.Row
    specs=[
      ('catalog','目前去重後有幾場比賽？','SELECT COUNT(*) AS n FROM catalog','SELECT COUNT(*) AS n FROM matches'),
      ('total_shots','去重後共有幾筆逐拍標註？','SELECT COUNT(*) AS n FROM annotations','SELECT COUNT(*) AS n FROM shots'),
      ('rally_count','去重後共有幾個回合？','SELECT COUNT(*) AS n FROM (SELECT match_name,set_no,rally FROM annotations GROUP BY match_name,set_no,rally)','SELECT COUNT(*) AS n FROM rallies'),
      ('years','依年份列出比賽數。','SELECT year,COUNT(*) AS n FROM catalog GROUP BY year ORDER BY year','SELECT year,COUNT(*) AS n FROM matches GROUP BY year ORDER BY year'),
      ('player_mapping','列出 2019 福州公開賽男單決賽的 A/B 球員姓名。',f"SELECT player_a,player_b FROM catalog WHERE name='{CHART_MATCH}'",f"SELECT player_a,player_b FROM matches WHERE name='{CHART_MATCH}'"),
      ('match_scope','2019 福州公開賽男單決賽共有幾筆逐拍標註？',f"SELECT COUNT(*) AS n FROM annotations WHERE match_name='{CHART_MATCH}'",f"SELECT COUNT(*) AS n FROM shots WHERE match_name='{CHART_MATCH}'"),
      ('chart','比較 2019 福州公開賽男單決賽兩位球員的出手數與比例並畫長條圖，player 使用 A/B。',f"SELECT player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM annotations WHERE match_name='{CHART_MATCH}'),2) AS pct FROM annotations WHERE match_name='{CHART_MATCH}' GROUP BY player ORDER BY player",f"SELECT player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM shots WHERE match_name='{CHART_MATCH}'),2) AS pct FROM shots WHERE match_name='{CHART_MATCH}' GROUP BY player ORDER BY player"),
      ('shot_distribution_2022','2022 年所有比賽各球種有幾筆標註？','SELECT s.type,COUNT(*) AS n FROM annotations s JOIN catalog m ON m.name=s.match_name WHERE m.year=2022 GROUP BY s.type ORDER BY s.type','SELECT s.type,COUNT(*) AS n FROM shots s JOIN matches m ON m.name=s.match_name WHERE m.year=2022 GROUP BY s.type ORDER BY s.type'),
      ('winners','2019 福州決賽 A/B 各有幾拍標記為落地致勝？',f"SELECT player,COUNT(*) AS n FROM annotations WHERE match_name='{CHART_MATCH}' AND win_reason='落地致勝' GROUP BY player ORDER BY player",f"SELECT player,COUNT(*) AS n FROM shots WHERE match_name='{CHART_MATCH}' AND win_reason='落地致勝' GROUP BY player ORDER BY player"),
      ('video_links','有幾場比賽提供外部影片連結？','SELECT COUNT(*) AS n FROM catalog WHERE video_url IS NOT NULL','SELECT COUNT(*) AS n FROM matches WHERE video_url IS NOT NULL'),
      ('video_link_scope','列出 2019 福州決賽的原始影片網址。',f"SELECT video_url FROM catalog WHERE name='{CHART_MATCH}'",f"SELECT video_url FROM matches WHERE name='{CHART_MATCH}'"),
      ('no_video','有幾個已具本機可播放影片的回合？','SELECT 0 AS n','SELECT COUNT(*) AS n FROM rallies WHERE has_video=1'),
      ('overlapping_matches','兩份來源共有幾場重疊比賽？','SELECT COUNT(*) AS n FROM (SELECT name FROM source_matches GROUP BY name HAVING COUNT(*)>1)','SELECT COUNT(*) AS n FROM (SELECT match_name FROM match_sources GROUP BY match_name HAVING COUNT(*)>1)'),
      ('deduplication','逐拍來源標註中去除了幾筆重複？','SELECT (SELECT COUNT(*) FROM source_shots)-(SELECT COUNT(*) FROM annotations) AS n','SELECT (SELECT COUNT(*) FROM shot_sources)-(SELECT COUNT(*) FROM shots) AS n'),
      ('source_counts','各資料來源有幾筆原始逐拍標註？','SELECT dataset,COUNT(*) AS n FROM source_shots GROUP BY dataset ORDER BY dataset','SELECT dataset,COUNT(*) AS n FROM shot_sources GROUP BY dataset ORDER BY dataset'),
      ('ambiguous_shot_numbers','有幾組拍號相同但內容不同的標註？','SELECT COUNT(*) AS n FROM (SELECT match_name,set_no,rally,ball_round FROM annotations GROUP BY match_name,set_no,rally,ball_round HAVING COUNT(*)>1)',"SELECT COUNT(*) AS n FROM data_quality_issues WHERE code='repeated_shot_number'"),
    ]
    cases=[]
    for ident,prompt,source_sql,target_sql in specs:
        expected=[dict(r) for r in db.execute(source_sql)]
        cases.append({'id':ident,'prompt':prompt,'source_sql':source_sql,'target_sql':target_sql,'expected':expected,'requires_chart':ident=='chart'})
    digest=logical_digest(db)
    db.close()
    temporary.replace(oracle)
    bank={'dataset':'shuttleset_merged','sources':sources,'source_sha256':digest,'source_hash_kind':'sqlite_rows_v1',
      'source_path':'results/data/shuttleset-oracle.db','chart_match':CHART_MATCH,
      'scope':'development oracle independently computed from source CSVs; not a model-quality evaluation','cases':cases}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'oracle':str(oracle),'bank':str(output),'cases':len(cases)}))
    return bank


def verify_frozen():
    if not OUTPUT.exists():
        raise ValueError('Missing frozen ShuttleSet benchmark')
    candidate=ORACLE.parent/'candidate-cases.json'
    try:
        current=create(output=candidate,refresh=True)
        if current!=json.loads(OUTPUT.read_text()):
            raise ValueError('Source archives differ from the frozen independent oracle; review before importing')
    finally:
        candidate.unlink(missing_ok=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--refresh',action='store_true');p.add_argument('--verify',action='store_true')
    args=p.parse_args()
    if args.verify:verify_frozen()
    else:create(refresh=args.refresh)

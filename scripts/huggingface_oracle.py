#!/usr/bin/env python3
"""Independent, stdlib-only CSV oracle for an authorized pinned HF snapshot."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sqlite3

ROOT=Path(__file__).resolve().parents[1]


def number(value,default=0):
    if value is None or not str(value).strip():return default
    return int(float(value))


def catalog(snapshot):
    grouped=defaultdict(list)
    for folder in sorted((Path(snapshot)/'Data').iterdir()):
        if folder.is_dir() and folder.name.endswith('.mp4'):
            key=re.sub(r'[^a-z0-9]','',folder.stem.lower())
            grouped[key].append(folder)
    selected={key:max(paths,key=lambda p:len(list((p/'label').glob('set*.csv')))) for key,paths in grouped.items()}
    return selected,grouped


def prepare(snapshot,output):
    snapshot,output=Path(snapshot),Path(output)
    manifest=json.loads((snapshot/'manifest.json').read_text())
    for entry in manifest['files']:
        path=snapshot/entry['path']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('HF cached CSV failed verification: '+entry['path'])
    output.mkdir(parents=True,exist_ok=True)
    dbpath=output/'hf-oracle.db'
    dbpath.unlink(missing_ok=True)
    db=sqlite3.connect(dbpath)
    db.executescript('''
    CREATE TABLE catalog(name TEXT PRIMARY KEY,folder TEXT,is_practice INTEGER,year INTEGER,player_a TEXT,player_b TEXT,video_url TEXT);
    CREATE TABLE annotations(match_name TEXT,set_no INTEGER,rally INTEGER,ball_round INTEGER,player TEXT,type TEXT,win_reason TEXT,roundscore_a INTEGER,roundscore_b INTEGER);
    CREATE TABLE segments(match_name TEXT,rally_id TEXT,set_no INTEGER,PRIMARY KEY(match_name,rally_id));
    CREATE TABLE videos(match_name TEXT,rally_id TEXT,path TEXT PRIMARY KEY);
    CREATE TABLE full_videos(path TEXT PRIMARY KEY);
    ''')
    selected,variants=catalog(snapshot)
    alias={folder.name:selected[key].stem for key,paths in variants.items() for folder in paths}
    for key,folder in selected.items():
        name=folder.stem
        practice=int(name.startswith('NYCU_Other_practice'))
        info_path=folder/'match_info.csv'
        info=next(csv.DictReader(info_path.open(encoding='utf-8-sig')), {}) if info_path.exists() else {}
        found=re.search(r'(20\d{2})',name)
        year=number(info['year']) if info.get('year') else (int(found[1]) if found else None)
        youtube=info.get('youtube_id','').strip()
        video='https://www.youtube.com/watch?v='+youtube if re.fullmatch(r'[A-Za-z0-9_-]{11}',youtube) else None
        db.execute('INSERT INTO catalog VALUES (?,?,?,?,?,?,?)',(name,folder.name,practice,year,info.get('player_a'),info.get('player_b'),video))
        if practice:continue
        for sn in (1,2,3):
            path=folder/'label'/f'set{sn}.csv'
            if not path.exists():continue
            with path.open(encoding='utf-8-sig',newline='') as file:
                for r in csv.DictReader(file):
                    kind=r.get('type','')
                    if '?' in kind or any(0xe000<=ord(c)<=0xf8ff for c in kind):kind='未知球種'
                    db.execute('INSERT INTO annotations VALUES (?,?,?,?,?,?,?,?,?)',(name,sn,number(r['rally']),number(r['ball_round']),r.get('player',''),kind,r.get('win_reason') or None,number(r.get('roundscore_A')),number(r.get('roundscore_B'))))
        path=folder/'RallySeg.csv'
        if path.exists():
            with path.open(encoding='utf-8-sig',newline='') as file:
                for r in csv.DictReader(file):
                    score=r['Score'].strip();parts=score.split('_');sn=int(parts[0]) if len(parts)==3 else 0
                    db.execute('INSERT OR REPLACE INTO segments VALUES (?,?,?)',(name,score,sn))
    inventory=json.loads((snapshot/'inventory.json').read_text())
    for entry in inventory['entries']:
        parts=entry['path'].split('/')
        if entry.get('type')=='file' and len(parts)==2 and parts[0]=='Video' and parts[1].endswith('.mp4'):
            db.execute('INSERT INTO full_videos VALUES (?)',(entry['path'],))
        if entry.get('type')=='file' and len(parts)==4 and parts[0]=='Data' and parts[2]=='rally_video' and parts[3].endswith('.mp4') and parts[1] in alias:
            db.execute('INSERT INTO videos VALUES (?,?,?)',(alias[parts[1]],Path(parts[3]).stem,entry['path']))
    db.execute('CREATE INDEX idx_oracle_annotations ON annotations(match_name)')
    db.commit();db.row_factory=sqlite3.Row
    chart='2025game1'
    if not db.execute('SELECT 1 FROM annotations WHERE match_name=?',(chart,)).fetchone():
        chart=db.execute('SELECT match_name FROM annotations GROUP BY match_name ORDER BY match_name LIMIT 1').fetchone()[0]
    # Expectations are computed before the production importer is run.
    specs=[
      ('catalog','列出目前 HF 目錄共有幾筆比賽／練習紀錄。','SELECT COUNT(*) AS n FROM catalog','SELECT COUNT(*) AS n FROM matches'),
      ('official_catalog','排除練習後，目錄共有幾場正式比賽？','SELECT COUNT(*) AS n FROM catalog WHERE is_practice=0','SELECT COUNT(*) AS n FROM matches WHERE is_practice=0'),
      ('practice_catalog','目錄有幾筆練習紀錄？','SELECT COUNT(*) AS n FROM catalog WHERE is_practice=1','SELECT COUNT(*) AS n FROM matches WHERE is_practice=1'),
      ('total_shots','目前 HF 正式比賽共有幾筆已匯入逐拍標註？','SELECT COUNT(*) AS n FROM annotations','SELECT COUNT(*) AS n FROM shots'),
      ('labeled_matches','有幾場比賽含逐拍標註？','SELECT COUNT(DISTINCT match_name) AS n FROM annotations','SELECT COUNT(DISTINCT match_name) AS n FROM shots'),
      ('rally_count','目前匯入幾個原始回合片段？','SELECT COUNT(*) AS n FROM segments','SELECT COUNT(*) AS n FROM rallies'),
      ('years','依年份統計正式比賽目錄數。','SELECT year,COUNT(*) AS n FROM catalog WHERE is_practice=0 GROUP BY year ORDER BY year','SELECT year,COUNT(*) AS n FROM matches WHERE is_practice=0 GROUP BY year ORDER BY year'),
      ('player_mapping',f'列出 {chart} 的 A/B 球員姓名。',f"SELECT player_a,player_b FROM catalog WHERE name='{chart}'",f"SELECT player_a,player_b FROM matches WHERE name='{chart}'"),
      ('chart',f'比較 {chart} 的 A/B 出手數與百分比並畫圖。',f"SELECT player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM annotations WHERE match_name='{chart}'),2) AS pct FROM annotations WHERE match_name='{chart}' GROUP BY player ORDER BY player",f"SELECT player,COUNT(*) AS n,ROUND(100.0*COUNT(*)/(SELECT COUNT(*) FROM shots WHERE match_name='{chart}'),2) AS pct FROM shots WHERE match_name='{chart}' GROUP BY player ORDER BY player"),
      ('shot_types','2025 年比賽的各球種標註數。','SELECT a.type,COUNT(*) AS n FROM annotations a JOIN catalog c ON c.name=a.match_name WHERE c.year=2025 GROUP BY a.type ORDER BY a.type','SELECT s.type,COUNT(*) AS n FROM shots s JOIN matches m ON m.name=s.match_name WHERE m.year=2025 GROUP BY s.type ORDER BY s.type'),
      ('remote_videos','HF 清單列有幾個遠端回合影片？','SELECT COUNT(*) AS n FROM videos','SELECT COUNT(*) AS n FROM remote_videos'),
      ('remote_match_videos','HF 清單列有幾個遠端全場影片？','SELECT COUNT(*) AS n FROM full_videos','SELECT COUNT(*) AS n FROM remote_match_videos'),
      ('remote_rallies','有幾個回合能在遠端影片清單找到對應？','SELECT COUNT(*) AS n FROM segments s WHERE EXISTS(SELECT 1 FROM videos v WHERE v.match_name=s.match_name AND v.rally_id=s.rally_id)','SELECT COUNT(*) AS n FROM rallies WHERE remote_video_available=1'),
      ('no_local_video','目前有幾個本機已下載可播放的回合影片？','SELECT 0 AS n','SELECT COUNT(*) AS n FROM rallies WHERE has_video=1'),
      ('video_links','有幾場比賽提供 YouTube 來源連結？','SELECT COUNT(*) AS n FROM catalog WHERE video_url IS NOT NULL','SELECT COUNT(*) AS n FROM matches WHERE video_url IS NOT NULL'),
      ('match_scope',f'{chart} 共有幾筆逐拍標註？',f"SELECT COUNT(*) AS n FROM annotations WHERE match_name='{chart}'",f"SELECT COUNT(*) AS n FROM shots WHERE match_name='{chart}'"),
      ('source_only','目前目錄有幾筆非 HF 來源？','SELECT 0 AS n',"SELECT COUNT(*) AS n FROM matches WHERE source!='hf'"),
    ]
    cases=[{'id':i,'prompt':p,'source_sql':s,'target_sql':t,'expected':[dict(r) for r in db.execute(s)],'requires_chart':i=='chart'} for i,p,s,t in specs]
    db.close()
    bank={'dataset':'huggingface','repo_id':manifest['repo_id'],'revision':manifest['revision'],
          'source_path':'results/data/hf-oracle.db','source_sha256':hashlib.sha256(dbpath.read_bytes()).hexdigest(),
          'chart_match':chart,'chart_players':next(c['expected'][0] for c in cases if c['id']=='player_mapping'),
          'cases':cases,'model_validation':'not_run'}
    (output/'hf_cases.json').write_text(json.dumps(bank,ensure_ascii=False,indent=2)+'\n')
    return bank

#!/usr/bin/env python3
"""Prepare and verify an HF DB offline, then back up and replace the active dataset."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

from huggingface_oracle import prepare
from sync_huggingface_data import CACHE, ROOT, sync

RUNTIME=ROOT/'.runtime/badminton-gpt'


def backup_active():
    source=RUNTIME/'data'
    if not (source/'badminton.db').exists():return None
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
    backup=RUNTIME/'backups'/('before-source-switch-'+stamp)
    shutil.copytree(source,backup)
    return str(backup.relative_to(ROOT))


def activate(revision=None):
    if revision and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Revision must be a complete commit SHA')
    if revision:
        snapshot=CACHE/revision
        if not (snapshot/'manifest.json').exists():sync(revision)
    else:
        pointer=CACHE/'current.json'
        if not pointer.exists():sync()
        current=json.loads(pointer.read_text());snapshot=ROOT/current['snapshot']
    source=json.loads((snapshot/'manifest.json').read_text())
    if source.get('repo_id')!='howard9199/Badminton':raise ValueError('Unexpected cached HF dataset')
    if source.get('skipped_large_csvs'):
        raise ValueError('Snapshot skipped large CSVs; keep the current DB until required annotations are available')
    stage_root=RUNTIME/'hf-build';stage_root.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='verified-',dir=stage_root) as temporary:
        stage=Path(temporary)
        prepare(snapshot,stage)
        image='badmintonai-db:7cccbb1'
        if subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['docker','compose','--env-file',str(ROOT/'.env'),'-f',str(ROOT/'compose.badminton-gpt.yml'),'build','badminton-db'],cwd=ROOT,check=True)
        subprocess.run(['docker','run','--rm','--network','none','--read-only','--tmpfs','/tmp','--user','0',
                        '-v',str(snapshot.resolve())+':/snapshot:ro',
                        '-v',str(stage.resolve())+':/output',
                        '-v',str(ROOT/'scripts/import_huggingface_data.py')+':/import_hf.py:ro',
                        image,'python3','/import_hf.py'],check=True,cwd=ROOT)
        manifest=json.loads((stage/'manifest.json').read_text())
        if manifest.get('dataset')!='huggingface' or manifest.get('videos_downloaded')!=0:
            raise ValueError('Invalid HF build result')
        backup=backup_active()
        data=RUNTIME/'data';data.mkdir(parents=True,exist_ok=True)
        # Only validated outputs replace the live database; manifest is switched last.
        for name in ('hf-oracle.db','hf_cases.json','badminton.db','manifest.json'):
            (stage/name).replace(data/name)
        print(json.dumps({'active_source':'huggingface','revision':manifest['revision'],'previous_data_backup':backup,'videos_downloaded':0}))
        return manifest


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--revision')
    activate(parser.parse_args().revision)

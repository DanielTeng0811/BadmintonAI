#!/usr/bin/env python3
"""Cache authorized Badminton CSVs at a pinned HF revision; never download videos."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'howard9199/Badminton'
CACHE = ROOT / '.runtime/badminton-gpt/huggingface'
MAX_FILE_BYTES = 8 * 1024 * 1024


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != 'https':
            raise ValueError('Refusing a non-HTTPS dataset redirect')
        target = super().redirect_request(req, fp, code, msg, headers, newurl)
        if target and urllib.parse.urlparse(req.full_url).hostname != urllib.parse.urlparse(newurl).hostname:
            target.remove_header('Authorization')
        return target


def load_token(env_path=ROOT / '.env'):
    for key in ('HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'):
        if os.environ.get(key):
            return os.environ[key]
    path = Path(env_path)
    if path.exists():
        for line in path.read_text().splitlines():
            match = re.fullmatch(r'\s*(?:export\s+)?(?:HF_TOKEN|HUGGING_FACE_HUB_TOKEN)\s*=\s*(.*?)\s*', line)
            if match:
                value = match.group(1).strip().strip('"\'')
                if value:
                    return value
    raise RuntimeError('Set HF_TOKEN in the ignored local .env; do not put it in command arguments')


def safe_path(path):
    value = PurePosixPath(path)
    if value.is_absolute() or '..' in value.parts or '\\' in path or '\x00' in path:
        raise ValueError('Invalid dataset path')
    return value


def verified_content(blob, entry):
    if len(blob) != entry['size']:
        return False
    lfs = entry.get('lfs') or {}
    if lfs.get('oid'):
        return hashlib.sha256(blob).hexdigest() == lfs['oid']
    if entry.get('oid'):
        git_blob = b'blob ' + str(len(blob)).encode() + b'\0' + blob
        return hashlib.sha1(git_blob).hexdigest() == entry['oid']
    return False


def fetch(url, token, *, label, max_bytes=16 * 1024 * 1024):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'huggingface.co':
        raise ValueError('Credentials may only be sent to Hugging Face over HTTPS')
    request = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + token, 'User-Agent': 'BadmintonAI-dataset-sync/1.0'})
    for attempt in range(4):
        try:
            with urllib.request.build_opener(SafeRedirect()).open(request, timeout=45) as response:
                blob = response.read(max_bytes + 1)
                if len(blob) > max_bytes:
                    raise RuntimeError(f'{label}: response exceeds size limit')
                return blob, response.headers
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 3:
                time.sleep(min(15, 2 ** attempt))
                continue
            # Do not include signed redirect URLs, request headers or response bodies.
            raise RuntimeError(f'{label}: HTTP {exc.code}') from None
        except (urllib.error.URLError, TimeoutError):
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f'{label}: network request failed') from None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.building.json')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def sync(revision=None, workers=6, max_file_bytes=MAX_FILE_BYTES):
    if max_file_bytes <= 0:
        raise ValueError('File size limit must be positive')
    token = load_token()
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    CACHE.chmod(0o700)
    if revision and not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Revision must be a complete commit SHA')
    info_blob, _ = fetch(f'https://huggingface.co/api/datasets/{REPO}', token, label='dataset metadata')
    info = json.loads(info_blob)
    revision = revision or info['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', revision):
        raise ValueError('Dataset revision must be a complete commit SHA')
    destination = CACHE / revision
    url = f'https://huggingface.co/api/datasets/{REPO}/tree/{revision}?recursive=true&limit=1000'
    entries = []
    while url:
        blob, headers = fetch(url, token, label='file inventory')
        entries.extend(json.loads(blob))
        match = re.search(r'<([^>]+)>;\s*rel="next"', headers.get('Link', ''))
        url = match.group(1) if match else None
    files = [e for e in entries if e.get('type') == 'file']
    all_csvs = [e for e in files if e['path'].lower().endswith('.csv')]
    csvs = [e for e in all_csvs if e['size'] <= max_file_bytes]
    skipped = [{'path': e['path'], 'bytes': e['size']} for e in all_csvs if e['size'] > max_file_bytes]
    videos = [e for e in files if e['path'].lower().endswith('.mp4')]
    if not csvs:
        raise RuntimeError('Dataset contains no CSVs')
    destination.mkdir(parents=True, exist_ok=True)
    write_json(destination / 'inventory.json', {'repo_id': REPO, 'revision': revision, 'entries': entries})

    def download(entry):
        relative = safe_path(entry['path'])
        path = destination.joinpath(*relative.parts)
        if path.is_file() and verified_content(path.read_bytes(), entry):
            blob, cached = path.read_bytes(), True
        else:
            address = f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/' + urllib.parse.quote(entry['path'], safe='/')
            blob, _ = fetch(address, token, label=entry['path'], max_bytes=max_file_bytes)
            if not verified_content(blob, entry):
                raise RuntimeError('Integrity verification failed: ' + entry['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + '.part')
            temporary.write_bytes(blob)
            temporary.replace(path)
            cached = False
        return {'path': entry['path'], 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest(), 'cached': cached}

    print(json.dumps({'repo_id': REPO, 'revision': revision, 'csv_files': len(csvs),
                      'csv_bytes': sum(e['size'] for e in csvs), 'video_files_not_downloaded': len(videos)}), flush=True)
    downloaded = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as executor:
        futures = [executor.submit(download, entry) for entry in csvs]
        for future in as_completed(futures):
            downloaded.append(future.result())
            if len(downloaded) % 50 == 0:
                print(json.dumps({'verified_csv_files': len(downloaded), 'total': len(csvs)}), flush=True)
    summary = {'repo_id': REPO, 'revision': revision, 'created_at': datetime.now(timezone.utc).isoformat(),
               'csv_files': len(downloaded), 'csv_bytes': sum(e['bytes'] for e in downloaded),
               'remote_video_files': len(videos), 'remote_video_bytes': sum(e['size'] for e in videos),
               'videos_downloaded': 0, 'active_database_modified': False,
               'max_file_bytes': max_file_bytes, 'skipped_large_csvs': skipped,
               'files': sorted(downloaded, key=lambda e: e['path'])}
    write_json(destination / 'manifest.json', summary)
    write_json(CACHE / 'current.json', {'repo_id': REPO, 'revision': revision, 'snapshot': str(destination.relative_to(ROOT))})
    print(json.dumps({k: v for k, v in summary.items() if k != 'files'}), flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', help='Pin a full dataset commit SHA')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--max-file-mb', type=int, default=8, help='Skip CSVs larger than this many MiB (default: 8)')
    args = parser.parse_args()
    try:
        sync(args.revision, args.workers, args.max_file_mb * 1024 * 1024)
    except (RuntimeError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')

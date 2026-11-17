"""Credential boundaries, source integrity and CSV-only HF synchronization."""
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import urllib.request

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hf_sync', ROOT/'scripts/sync_huggingface_data.py')
syncer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(syncer)


def test_token_stays_in_local_settings_and_environment_wins(tmp_path,monkeypatch):
    monkeypatch.delenv('HF_TOKEN',raising=False)
    monkeypatch.delenv('HUGGING_FACE_HUB_TOKEN',raising=False)
    settings=tmp_path/'.env'
    settings.write_text('OPENAI_API_KEY=other-service\nHF_TOKEN="hf_fixture_only"\n')
    assert syncer.load_token(settings)=='hf_fixture_only'
    monkeypatch.setenv('HF_TOKEN','hf_environment_fixture')
    assert syncer.load_token(settings)=='hf_environment_fixture'
    monkeypatch.delenv('HF_TOKEN')
    with pytest.raises(RuntimeError):syncer.load_token(tmp_path/'missing.env')


def test_redirect_drops_credentials_for_signed_cdn_urls():
    handler=syncer.SafeRedirect()
    request=urllib.request.Request('https://huggingface.co/datasets/example',headers={'Authorization':'Bearer hf_test_only'})
    same=handler.redirect_request(request,None,302,'Found',{},'https://huggingface.co/other')
    assert same.get_header('Authorization')=='Bearer hf_test_only'
    external=handler.redirect_request(request,None,302,'Found',{},'https://cdn.example.invalid/blob')
    assert not external.has_header('Authorization')
    with pytest.raises(ValueError):handler.redirect_request(request,None,302,'Found',{},'http://huggingface.co/blob')


@pytest.mark.parametrize('path',['../outside.csv','/absolute.csv','Data/../../secret.csv','Data\\secret.csv','Data/\x00.csv'])
def test_unsafe_repository_paths_rejected(path):
    with pytest.raises(ValueError):syncer.safe_path(path)


def test_remote_oid_verification_detects_corruption():
    blob=b'a,b\n1,2\n'
    oid=hashlib.sha1(b'blob '+str(len(blob)).encode()+b'\0'+blob).hexdigest()
    entry={'size':len(blob),'oid':oid}
    assert syncer.verified_content(blob,entry)
    assert not syncer.verified_content(blob.replace(b'1',b'9'),entry)
    assert syncer.verified_content(blob,{'size':len(blob),'lfs':{'oid':hashlib.sha256(blob).hexdigest()}})


def test_response_body_is_bounded_even_if_server_exceeds_inventory_size(monkeypatch):
    class Response(io.BytesIO):
        headers = {}
    class Opener:
        def open(self, *args, **kwargs):
            return Response(b'12345')
    monkeypatch.setattr(syncer.urllib.request, 'build_opener', lambda *args: Opener())
    with pytest.raises(RuntimeError, match='size limit'):
        syncer.fetch('https://huggingface.co/datasets/fixture', 'hf_fixture', label='fixture', max_bytes=4)
    assert syncer.fetch('https://huggingface.co/datasets/fixture', 'hf_fixture', label='fixture', max_bytes=5)[0] == b'12345'


def test_sync_downloads_only_csv_and_repairs_corrupt_cache(tmp_path,monkeypatch):
    revision='a'*40
    payload=b'player,type\nA,smash\n'
    oid=hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
    tree=[{'type':'file','path':'Data/match.mp4/label/set1.csv','size':len(payload),'oid':oid},
          {'type':'file','path':'Data/match.mp4/rally_video/1_00_01.mp4','size':5000000,'oid':'b'*40},
          {'type':'file','path':'Data/huge.csv','size':syncer.MAX_FILE_BYTES+1,'oid':'c'*40}]
    calls=[]
    def fetch(url,token,*,label,**kwargs):
        calls.append(url)
        if '/api/datasets/' in url and '/tree/' not in url:return json.dumps({'sha':revision}).encode(),{}
        if '/tree/' in url:return json.dumps(tree).encode(),{}
        assert url.endswith('/label/set1.csv')
        return payload,{}
    monkeypatch.setattr(syncer,'ROOT',tmp_path)
    monkeypatch.setattr(syncer,'CACHE',tmp_path/'.runtime/hf')
    monkeypatch.setattr(syncer,'load_token',lambda:'hf_fixture_only')
    monkeypatch.setattr(syncer,'fetch',fetch)
    result=syncer.sync(workers=2)
    assert result['csv_files']==1 and result['videos_downloaded']==0
    assert result['active_database_modified'] is False
    assert result['skipped_large_csvs']==[{'path':'Data/huge.csv','bytes':syncer.MAX_FILE_BYTES+1}]
    assert not any(url.endswith('/huge.csv') for url in calls)
    assert not any(url.endswith('1_00_01.mp4') for url in calls)
    assert syncer.sync()['files'][0]['cached'] is True
    (syncer.CACHE/revision/tree[0]['path']).write_bytes(b'corrupt')
    repaired=syncer.sync()
    assert repaired['files'][0]['cached'] is False
    assert (syncer.CACHE/revision/tree[0]['path']).read_bytes()==payload
    assert 'hf_fixture_only' not in (syncer.CACHE/revision/'manifest.json').read_text()

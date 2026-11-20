import json
from pathlib import Path
import pytest
from astra_hybrid.hybrid_router import load_config, resolve
from astra_hybrid.knowledge_hub import submit, list_records, review, propose_agent_exchange
from astra_hybrid.api_ingest import ingest


def test_all_four_engines_have_local_and_online():
    cfg=load_config()
    assert set(cfg['engines']) == {'VAJRA','AGNI','VAYU','ASTRA'}
    for e in cfg['engines'].values(): assert e['local']['provider'] and e['online']['provider']


def test_local_first_auto_does_not_require_cloud_secrets(monkeypatch):
    monkeypatch.setattr('astra_hybrid.hybrid_router.shutil.which', lambda _: '/usr/bin/espeak-ng')
    r=resolve('VAYU','auto',environ={})
    assert r['selected_mode']=='local' and r['provider']=='espeak_ng'


def test_online_requires_explicit_secrets():
    r=resolve('AGNI','online',environ={})
    assert not r['ready'] and r['selected_mode'] is None
    r=resolve('AGNI','online',environ={'ASTRA_CLOUD_URL':'https://x','ASTRA_CLOUD_TOKEN':'t'})
    assert r['ready'] and r['selected_mode']=='online'


def test_unknown_engine_and_mode_rejected():
    with pytest.raises(ValueError): resolve('NOPE')
    with pytest.raises(ValueError): resolve('VAJRA','magic')


def test_knowledge_starts_pending_and_requires_review(tmp_path):
    db=tmp_path/'hub.sqlite3'
    rid=submit('browser','browser-1','VAJRA','Hindi','Evidence',db=db)
    rows=list_records('pending',db=db)
    assert len(rows)==1 and rows[0]['id']==rid
    assert review(rid,'approved','owner',db=db)
    assert list_records('pending',db=db)==[]
    assert list_records('approved',db=db)[0]['id']==rid


def test_agent_exchange_is_proposal_not_direct_memory_write(tmp_path):
    db=tmp_path/'hub.sqlite3'
    rid=propose_agent_exchange('AGNI-agent','VAYU','phoneme','proposal',db=db)
    row=list_records('pending',db=db)[0]
    assert row['id']==rid and json.loads(row['metadata_json'])['requires_human_review'] is True


def test_api_source_disabled_and_http_rejected():
    with pytest.raises(ValueError,match='disabled'):
        ingest({'enabled':False})
    with pytest.raises(ValueError,match='HTTPS'):
        ingest({'enabled':True,'kind':'rest_json_get','base_url':'http://api.example.org','allowed_hosts':['api.example.org']})


def test_api_host_allowlist_required():
    with pytest.raises(ValueError,match='allowlisted'):
        ingest({'enabled':True,'kind':'rest_json_get','base_url':'https://evil.example','allowed_hosts':['api.example.org']})


def test_api_ingest_stores_pending_without_external_network(tmp_path, monkeypatch):
    import io
    class FakeResponse(io.BytesIO):
        headers={"Content-Type":"application/json"}
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
    class FakeOpener:
        def open(self, req, timeout=15): return FakeResponse(b'{"items":["hindi"]}')
    monkeypatch.setattr('urllib.request.build_opener', lambda *handlers: FakeOpener())
    monkeypatch.setattr('astra_hybrid.api_ingest.socket.getaddrinfo', lambda *a,**k: [(None,None,None,None,('93.184.216.34',443))])
    db=tmp_path/'hub.sqlite3'
    source={'id':'demo','enabled':True,'kind':'rest_json_get','base_url':'https://api.example.org/v1/',
            'allowed_hosts':['api.example.org'],'path':'docs','max_bytes':10000,'purpose':'test'}
    result=ingest(source, target_engine='VAJRA', db=db)
    assert result['ok'] and result['status']=='pending_review'
    row=list_records('pending',engine='VAJRA',db=db)[0]
    assert row['source_type']=='api' and 'hindi' in row['content']


def test_cloud_client_requires_https_and_token():
    from astra_hybrid.cloud_client import render_remote
    with pytest.raises(ValueError, match='HTTPS'):
        render_remote('AGNI','hello','/tmp/no.wav',base_url='http://cloud.example',token='secret')
    with pytest.raises(ValueError, match='TOKEN'):
        render_remote('VAYU','hello','/tmp/no.wav',base_url='https://cloud.example',token='')


def test_cloud_client_writes_valid_wav_atomically(tmp_path, monkeypatch):
    import io
    from astra_hybrid.cloud_client import render_remote
    class FakeResponse(io.BytesIO):
        headers={'Content-Type':'audio/wav'}
        def __enter__(self): return self
        def __exit__(self,*args): self.close()
    wav=b'RIFF'+b'\x00'*1000
    monkeypatch.setattr('urllib.request.build_opener', lambda *handlers: type('O',(),{'open':lambda self,req,timeout=150: FakeResponse(wav)})())
    out=render_remote('AGNI','नमस्ते',tmp_path/'remote.wav',base_url='https://cloud.example',token='secret')
    assert out.read_bytes()==wav and not out.with_suffix('.wav.part').exists()


def test_cloud_client_submits_knowledge_as_pending(tmp_path, monkeypatch):
    import io
    from astra_hybrid.cloud_client import submit_remote_knowledge
    class FakeResponse(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*args): self.close()
    payload=b'{"ok":true,"record_id":"abc123","status":"pending_review"}'
    monkeypatch.setattr('urllib.request.build_opener', lambda *handlers: type('O',(),{'open':lambda self,req,timeout=30: FakeResponse(payload)})())
    result=submit_remote_knowledge('agent','VAJRA-agent','VAJRA','Hindi','Evidence',
      base_url='https://cloud.example',token='secret')
    assert result['status']=='pending_review'

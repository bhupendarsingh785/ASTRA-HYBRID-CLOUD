import io, json, socket
from pathlib import Path
import pytest
from astra_hybrid.hybrid_router import resolve
from astra_hybrid.tts_runtime import synthesize
from astra_hybrid.quality_feedback import record, report, SCORES
from astra_hybrid.api_ingest import ingest


def test_cloud_text_is_blocked_without_explicit_consent(tmp_path):
    env={'ASTRA_CLOUD_URL':'https://cloud.example','ASTRA_CLOUD_TOKEN':'x'*40}
    def local(*a): raise RuntimeError('local failed')
    def online(*a): return a[2]
    with pytest.raises(PermissionError,match='Cloud text transfer'):
        synthesize('AGNI','नमस्ते',tmp_path/'out.wav','online',env,local,online)


def test_synthesizer_executes_local_route(tmp_path, monkeypatch):
    monkeypatch.setattr('astra_hybrid.hybrid_router.shutil.which',lambda _: '/usr/bin/espeak-ng')
    env={}
    def local(engine,text,out,environ):
        out.write_bytes(b'RIFF'+b'x'*2000); return out
    result=synthesize('VAYU','नमस्ते',tmp_path/'vayu.wav','local',env,local,lambda *a: None)
    assert result['ok'] and result['mode_used']=='local' and Path(result['output']).read_bytes().startswith(b'RIFF')


def test_auto_fallback_only_when_consent_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr('astra_hybrid.hybrid_router.shutil.which',lambda _: '/usr/bin/espeak-ng')
    env={'ASTRA_CLOUD_URL':'https://cloud.example','ASTRA_CLOUD_TOKEN':'x'*40,'ASTRA_ALLOW_CLOUD_TEXT':'1'}
    calls=[]
    def local(*a): calls.append('local'); raise RuntimeError('local broken')
    def online(engine,text,out,environ): calls.append('online'); out.write_bytes(b'RIFF'+b'x'*2000); return out
    result=synthesize('VAYU','नमस्ते',tmp_path/'fallback.wav','auto',env,local,online)
    assert result['fallback_used'] is True and calls==['local','online']


def test_auto_does_not_fallback_without_consent(tmp_path, monkeypatch):
    monkeypatch.setattr('astra_hybrid.hybrid_router.shutil.which',lambda _: '/usr/bin/espeak-ng')
    env={'ASTRA_CLOUD_URL':'https://cloud.example','ASTRA_CLOUD_TOKEN':'x'*40}
    calls=[]
    def local(*a): calls.append('local'); raise RuntimeError('broken')
    def online(*a): calls.append('online')
    with pytest.raises(RuntimeError,match='All permitted'):
        synthesize('VAYU','नमस्ते',tmp_path/'x.wav','auto',env,local,online)
    assert calls==['local']


def test_elevenlabs_requires_voice_id_and_key():
    r=resolve('ASTRA','online',environ={'ELEVENLABS_API_KEY':'x'})
    assert not r['ready']
    r=resolve('ASTRA','online',environ={'ELEVENLABS_API_KEY':'x','ELEVENLABS_VOICE_ID':'voice1'})
    assert r['ready']


def test_personal_local_adapter_requires_placeholders():
    r=resolve('ASTRA','local',environ={'ASTRA_LOCAL_TTS_COMMAND':json.dumps(['python','x.py'])})
    assert not r['ready']


def test_tiny_tts_requires_explicit_remote_code_opt_in(tmp_path):
    r=resolve('VAJRA','local',environ={'ASTRA_INDIC_TINY_TTS_MODEL_DIR':str(tmp_path)})
    assert not r['ready'] and 'Review pinned' in r['checks']['local']['detail']


def test_quality_feedback_is_per_engine_and_never_auto_trains(tmp_path):
    audio=tmp_path/'sample.wav'; audio.write_bytes(b'RIFF'+b'x'*2000)
    scores={k:4 for k in SCORES}
    rid=record('AGNI','sample-01',audio,scores,'clear Hindi','piper-hi-v1',False,tmp_path/'db.sqlite')
    r=report(db=tmp_path/'db.sqlite')
    assert r['count']==1 and r['engines']['AGNI']['count']==1
    assert r['engines']['AGNI']['training_consented']==0 and len(rid)==24


def test_quality_feedback_rejects_missing_dimensions(tmp_path):
    audio=tmp_path/'sample.wav'; audio.write_bytes(b'RIFF'+b'x'*2000)
    with pytest.raises(ValueError): record('VAYU','x',audio,{'naturalness':5},db=tmp_path/'db.sqlite')


def test_api_ingest_blocks_private_dns_even_when_host_allowlisted(tmp_path,monkeypatch):
    monkeypatch.setattr('astra_hybrid.api_ingest.socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    source={'id':'x','enabled':True,'kind':'rest_json_get','base_url':'https://api.example.org/','allowed_hosts':['api.example.org'],'path':'v1'}
    with pytest.raises(ValueError,match='non-public IP'):
        ingest(source,db=tmp_path/'db.sqlite')


def test_api_ingest_blocks_non_json_content_type(tmp_path,monkeypatch):
    class Resp(io.BytesIO):
        headers={'Content-Type':'text/html'}
        def __enter__(self): return self
        def __exit__(self,*a): self.close()
    class Opener:
        def open(self,*a,**k): return Resp(b'<html>')
    monkeypatch.setattr('astra_hybrid.api_ingest.socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('93.184.216.34',443))])
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
    source={'id':'x','enabled':True,'kind':'rest_json_get','base_url':'https://api.example.org/','allowed_hosts':['api.example.org'],'path':'v1'}
    with pytest.raises(ValueError,match='application/json'):
        ingest(source,db=tmp_path/'db.sqlite')


def test_cloud_knowledge_review_client_uses_authenticated_endpoint(monkeypatch):
    from astra_hybrid.cloud_client import review_remote_knowledge
    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*a): self.close()
    payload=b'{"ok":true,"status":"approved"}'
    class Opener:
        def open(self,req,timeout=30):
            assert req.full_url=='https://cloud.example/v1/knowledge/review'
            assert req.get_header('Authorization')=='Bearer '+'z'*40
            return Resp(payload)
    monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
    r=review_remote_knowledge('abc','approved',base_url='https://cloud.example',token='z'*40)
    assert r['status']=='approved'


def test_local_engine_writes_output_atomically(tmp_path, monkeypatch):
    from astra_hybrid.tts_runtime import _run_local
    monkeypatch.setattr('shutil.which',lambda _: '/usr/bin/espeak-ng')
    def fake_run(cmd,**kwargs):
        Path(cmd[cmd.index('-w')+1]).write_bytes(b'RIFF'+b'x'*1200)
    monkeypatch.setattr('subprocess.run',fake_run)
    out=tmp_path/'out.wav'
    result=_run_local('VAYU','नमस्ते',out,{})
    assert result==out and out.exists() and not (tmp_path/'out.wav.part').exists()


def test_approved_knowledge_can_be_retrieved_per_engine(tmp_path):
    from astra_hybrid.knowledge_hub import submit, review, search_records
    db=tmp_path/'hub.sqlite3'
    rid=submit('browser','source-1','AGNI','Hindi pronunciation','यह नमस्ते उच्चारण का प्रमाण है',db=db)
    assert search_records('नमस्ते','AGNI',db=db)==[]
    assert review(rid,'approved','owner',db=db)
    rows=search_records('नमस्ते','AGNI',db=db)
    assert len(rows)==1 and rows[0]['status']=='approved'
    assert search_records('नमस्ते','VAYU',db=db)==[]


def test_knowledge_search_rejects_empty_and_oversized_query(tmp_path):
    from astra_hybrid.knowledge_hub import search_records
    with pytest.raises(ValueError): search_records('',db=tmp_path/'db.sqlite')
    with pytest.raises(ValueError): search_records('x'*201,db=tmp_path/'db.sqlite')


def test_piper_18_cli_contract_is_used_for_local_engine(tmp_path, monkeypatch):
    from astra_hybrid.tts_runtime import _run_local
    model=tmp_path/'hindi.onnx'; model.write_bytes(b'model')
    Path(str(model)+'.json').write_text('{}',encoding='utf-8')
    seen={}
    def fake_run(cmd,**kwargs):
        seen['cmd']=cmd
        Path(cmd[cmd.index('-f')+1]).write_bytes(b'RIFF'+b'x'*1200)
    monkeypatch.setattr('shutil.which',lambda _: '/usr/bin/python')
    monkeypatch.setattr('subprocess.run',fake_run)
    out=tmp_path/'agni.wav'
    _run_local('AGNI','नमस्ते',out,{'PYTHON':'python','PIPER_MODEL_PATH':str(model)})
    assert seen['cmd'][1:3]==['-m','piper']
    assert seen['cmd'][seen['cmd'].index('-m')+1]=='piper'
    assert out.exists()


def test_api_ingest_rejects_arbitrary_auth_header(tmp_path, monkeypatch):
    monkeypatch.setattr('astra_hybrid.api_ingest.socket.getaddrinfo',lambda *a,**k:[(None,None,None,None,('93.184.216.34',443))])
    source={'id':'x','enabled':True,'kind':'rest_json_get','base_url':'https://api.example.org/','allowed_hosts':['api.example.org'],
            'path':'v1','auth_env':'API_SECRET','auth_header':'X-Injected-Header'}
    with pytest.raises(ValueError,match='unsupported or unsafe'):
        ingest(source,environ={'API_SECRET':'secret'},db=tmp_path/'db.sqlite')


def test_elevenlabs_runtime_saves_mp3_and_uses_zero_retention(tmp_path, monkeypatch):
    from astra_hybrid.tts_runtime import _run_elevenlabs
    class Resp(io.BytesIO):
        headers={'Content-Type':'audio/mpeg'}
        def __enter__(self): return self
        def __exit__(self,*a): self.close()
    captured={}
    def fake_open(req,timeout=90):
        captured['url']=req.full_url
        captured['key']=req.get_header('Xi-api-key')
        captured['body']=json.loads(req.data.decode())
        return Resp(b'ID3'+b'x'*1000)
    monkeypatch.setattr('urllib.request.urlopen',fake_open)
    out=tmp_path/'astra.mp3'
    _run_elevenlabs('नमस्ते',out,{'ELEVENLABS_API_KEY':'secret','ELEVENLABS_VOICE_ID':'voice-1','ELEVENLABS_ZERO_RETENTION':'1'})
    assert out.read_bytes().startswith(b'ID3')
    assert 'enable_logging=false' in captured['url'] and captured['key']=='secret'
    assert captured['body']['text']=='नमस्ते'


def test_elevenlabs_runtime_rejects_wrong_extension(tmp_path):
    from astra_hybrid.tts_runtime import _run_elevenlabs
    with pytest.raises(ValueError,match='mp3'):
        _run_elevenlabs('नमस्ते',tmp_path/'bad.wav',{})

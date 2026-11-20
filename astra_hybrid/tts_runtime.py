"""Real hybrid TTS execution for ASTRA engines.

No credentials are embedded. Cloud transmission is blocked unless the operator
sets ASTRA_ALLOW_CLOUD_TEXT=1. Outputs are written atomically and validated.
"""
from __future__ import annotations
import asyncio, json, os, shutil, subprocess, tempfile, urllib.parse, urllib.request
from pathlib import Path
from typing import Callable
from .hybrid_router import resolve

MAX_TEXT_CHARS = 8000

def _atomic_bytes(out: Path, data: bytes, minimum: int = 256) -> Path:
    if len(data) < minimum: raise RuntimeError("TTS provider returned an empty or suspiciously small audio file")
    if out.suffix.lower() == ".wav" and not data.startswith(b"RIFF"): raise RuntimeError("TTS provider did not return a RIFF/WAV file")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        tmp.write_bytes(data); tmp.replace(out)
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass
    return out

def _run_local(engine: str, text: str, out: Path, env: dict[str,str]) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp=out.with_name(out.name+".part")
    try:
        if engine == "AGNI":
            python=env.get("PYTHON", "python")
            model=env.get("PIPER_MODEL_PATH", "")
            if not shutil.which(python) or not model or not Path(model).is_file() or not Path(model+".json").is_file():
                raise RuntimeError("Python, Piper package, Hindi ONNX model and matching .onnx.json config are required")
            subprocess.run([python,"-m","piper","-m",model,"-f",str(tmp),"--",text],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=True)
        elif engine == "VAYU":
            binary=shutil.which("espeak-ng")
            if not binary: raise RuntimeError("espeak-ng is not installed")
            subprocess.run([binary,"-v",env.get("ESPEAK_VOICE","hi"),"-w",str(tmp),text],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True)
        elif engine == "VAJRA":
            model=env.get("ASTRA_INDIC_TINY_TTS_MODEL_DIR", "")
            if not model: raise RuntimeError("ASTRA_INDIC_TINY_TTS_MODEL_DIR is not configured")
            if env.get("ASTRA_ALLOW_TINY_TTS_REMOTE_CODE") != "1":
                raise PermissionError("Review the pinned Indic Tiny TTS upstream code, then set ASTRA_ALLOW_TINY_TTS_REMOTE_CODE=1")
            cmd=[env.get("PYTHON", "python"),"-m","swar.tools.tiny_tts_render","--allow-remote-code","--model-dir",model,
                 "--backend",env.get("ASTRA_TINY_TTS_BACKEND","onnx"),"--voice",env.get("ASTRA_TINY_TTS_VOICE","female"),"--text",text,"--out",str(tmp)]
            subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=True)
        elif engine == "ASTRA":
            raw=env.get("ASTRA_LOCAL_TTS_COMMAND", "")
            if not raw: raise RuntimeError("ASTRA_LOCAL_TTS_COMMAND is not configured for your personal local voice model")
            command=json.loads(raw)
            if not isinstance(command,list) or not command or not all(isinstance(x,str) for x in command): raise RuntimeError("ASTRA_LOCAL_TTS_COMMAND must be a JSON string array")
            with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".txt",delete=False) as f:
                f.write(text); text_path=Path(f.name)
            try:
                args=[x.replace("{text_file}",str(text_path)).replace("{output_file}",str(tmp)) for x in command]
                if not any("{text_file}" in x for x in command) or not any("{output_file}" in x for x in command):
                    raise RuntimeError("personal adapter command must include {text_file} and {output_file} placeholders")
                subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=True)
            finally:
                text_path.unlink(missing_ok=True)
        else: raise ValueError("unknown engine")
        if not tmp.is_file(): raise RuntimeError("local TTS command did not create its output file")
        data=tmp.read_bytes()
        if tmp.suffix.lower()==".wav" and (len(data)<1000 or not data.startswith(b"RIFF")): raise RuntimeError("local TTS produced invalid WAV")
        if tmp.suffix.lower()!=".wav" and len(data)<256: raise RuntimeError("local TTS produced an invalid audio file")
        tmp.replace(out)
        return out
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass

def _run_edge(text: str, out: Path, env: dict[str,str]) -> Path:
    if out.suffix.lower() != ".mp3": raise ValueError("EDGE online output must use a .mp3 filename")
    try: import edge_tts
    except ImportError as exc: raise RuntimeError("install edge-tts to use VAJRA online EDGE provider") from exc
    tmp=out.with_name(out.name+".part")
    async def _go():
        voice=env.get("EDGE_TTS_VOICE","hi-IN-SwaraNeural")
        await edge_tts.Communicate(text,voice).save(str(tmp))
    try:
        asyncio.run(_go())
        if not tmp.is_file() or tmp.stat().st_size<256: raise RuntimeError("EDGE provider returned no audio")
        tmp.replace(out)
        return out
    finally:
        try: tmp.unlink()
        except FileNotFoundError: pass

def _run_elevenlabs(text: str, out: Path, env: dict[str,str]) -> Path:
    if out.suffix.lower() != ".mp3": raise ValueError("ElevenLabs output must use a .mp3 filename")
    key=env.get("ELEVENLABS_API_KEY",""); voice=env.get("ELEVENLABS_VOICE_ID","")
    if not key or not voice: raise RuntimeError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required")
    query=urllib.parse.urlencode({"output_format":env.get("ELEVENLABS_OUTPUT_FORMAT","mp3_44100_128"),"enable_logging":"false" if env.get("ELEVENLABS_ZERO_RETENTION","1")=="1" else "true"})
    url="https://api.elevenlabs.io/v1/text-to-speech/"+urllib.parse.quote(voice,safe="")+"?"+query
    body=json.dumps({"text":text,"model_id":env.get("ELEVENLABS_MODEL_ID","eleven_multilingual_v2")},ensure_ascii=False).encode()
    req=urllib.request.Request(url,data=body,headers={"xi-api-key":key,"Content-Type":"application/json","Accept":"audio/mpeg"},method="POST")
    with urllib.request.urlopen(req,timeout=90) as response:
        if response.headers.get("Content-Type","").split(";",1)[0] not in {"audio/mpeg","audio/mp3","application/octet-stream"}:
            raise RuntimeError("ElevenLabs returned an unexpected content type")
        data=response.read(25_000_001)
    if len(data)>25_000_000: raise RuntimeError("ElevenLabs audio response exceeded 25 MB")
    return _atomic_bytes(out,data)

def _run_online(engine: str, text: str, out: Path, env: dict[str,str]) -> Path:
    if engine=="VAJRA": return _run_edge(text,out,env)
    if engine=="ASTRA": return _run_elevenlabs(text,out,env)
    from .cloud_client import render_remote
    return render_remote(engine,text,out,base_url=env.get("ASTRA_CLOUD_URL"),token=env.get("ASTRA_CLOUD_TOKEN"))

def synthesize(engine: str, text: str, output_path: str | Path, mode: str = "auto",
               environ: dict[str,str] | None = None,
               local_runner: Callable | None = None, online_runner: Callable | None = None) -> dict:
    """Execute selected backend. Auto fallback to cloud is privacy-consent gated."""
    env=os.environ if environ is None else environ
    key=engine.upper(); out=Path(output_path)
    if not isinstance(text,str) or not text.strip() or len(text)>MAX_TEXT_CHARS: raise ValueError("text must be 1..8000 characters")
    plan=resolve(key,mode,environ=env)
    if not plan["ready"]: raise RuntimeError("No requested backend is ready: "+json.dumps(plan["checks"],ensure_ascii=False))
    selected=plan["selected_mode"]
    if selected=="online" and env.get("ASTRA_ALLOW_CLOUD_TEXT")!="1":
        raise PermissionError("Cloud text transfer is disabled. Set ASTRA_ALLOW_CLOUD_TEXT=1 only after approving this privacy choice.")
    runners={"local":local_runner or _run_local,"online":online_runner or _run_online}
    errors=[]
    order=[selected]
    if mode=="auto" and selected=="local" and env.get("ASTRA_ALLOW_CLOUD_TEXT")=="1":
        other="online"
        if plan["checks"][other]["ready"]: order.append(other)
    for route in order:
        try:
            out.unlink(missing_ok=True)
            result=runners[route](key,text,out,env)
            return {"ok":True,"engine":key,"mode_used":route,"provider":plan["checks"][route]["detail"],"output":str(result),"fallback_used":route!=selected,"errors":errors}
        except Exception as exc:
            errors.append({"mode":route,"error":type(exc).__name__+": "+str(exc)[:240]})
            if route=="online" or len(order)==1: break
    raise RuntimeError("All permitted TTS routes failed: "+json.dumps(errors,ensure_ascii=False))

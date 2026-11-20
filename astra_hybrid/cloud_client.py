"""Authenticated client for the ASTRA user's own self-hosted Piper/eSpeak worker."""
from __future__ import annotations
import json, os, urllib.error, urllib.request
from pathlib import Path

def render_remote(engine: str, text: str, output_path: str | Path,
                  base_url: str | None = None, token: str | None = None, timeout: int = 150) -> Path:
    engine=engine.upper()
    if engine not in {"AGNI", "VAYU"}: raise ValueError("personal cloud TTS currently supports AGNI and VAYU only")
    if not text.strip() or len(text)>8000: raise ValueError("text must be 1..8000 characters")
    base=(base_url or os.environ.get("ASTRA_CLOUD_URL", "")).rstrip("/")
    secret=token or os.environ.get("ASTRA_CLOUD_TOKEN", "")
    if not base.startswith("https://"): raise ValueError("ASTRA_CLOUD_URL must use HTTPS")
    if not secret: raise ValueError("ASTRA_CLOUD_TOKEN is required")
    payload=json.dumps({"engine":engine,"text":text},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(base+"/v1/tts",data=payload,headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"},method="POST")
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener=urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req,timeout=timeout) as response:
            audio=response.read(30_000_001)
            if len(audio)>30_000_000: raise RuntimeError("cloud audio exceeded 30 MB")
            if response.headers.get("Content-Type","").split(";")[0] != "audio/wav": raise RuntimeError("cloud did not return audio/wav")
    except urllib.error.HTTPError as exc:
        detail=exc.read(4000).decode("utf-8",errors="replace")
        raise RuntimeError(f"ASTRA cloud returned HTTP {exc.code}: {detail}") from exc
    if len(audio)<1000 or not audio.startswith(b"RIFF"): raise RuntimeError("cloud returned an invalid or incomplete WAV")
    out=Path(output_path); out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix(out.suffix+".part")
    tmp.write_bytes(audio); tmp.replace(out)
    return out


def submit_remote_knowledge(source_type: str, source_id: str, target_engine: str,
                            topic: str, content: str, metadata: dict | None = None,
                            base_url: str | None = None, token: str | None = None,
                            timeout: int = 30) -> dict:
    """Send browser/API/agent evidence to the personal cloud review inbox."""
    import json
    base=(base_url or os.environ.get("ASTRA_CLOUD_URL", "")).rstrip("/")
    secret=token or os.environ.get("ASTRA_CLOUD_TOKEN", "")
    if not base.startswith("https://"): raise ValueError("ASTRA_CLOUD_URL must use HTTPS")
    if not secret: raise ValueError("ASTRA_CLOUD_TOKEN is required")
    body=json.dumps({"source_type":source_type,"source_id":source_id,"target_engine":target_engine,
                     "topic":topic,"content":content,"metadata":metadata or {}},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(base+"/v1/knowledge/submit",data=body,
      headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"},method="POST")
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener=urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req,timeout=timeout) as response:
            payload=json.loads(response.read(16_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read(4000).decode("utf-8",errors="replace")
        raise RuntimeError(f"ASTRA cloud returned HTTP {exc.code}: {detail}") from exc
    if not payload.get("ok") or payload.get("status") != "pending_review":
        raise RuntimeError("ASTRA cloud did not accept the knowledge proposal")
    return payload


def review_remote_knowledge(record_id: str, decision: str, reviewer: str = "owner",
                           base_url: str | None = None, token: str | None = None, timeout: int = 30) -> dict:
    """Approve/reject one pending cloud knowledge proposal with the owner token."""
    if decision not in {"approved", "rejected"}: raise ValueError("decision must be approved/rejected")
    base=(base_url or os.environ.get("ASTRA_CLOUD_URL", "")).rstrip("/")
    secret=token or os.environ.get("ASTRA_CLOUD_TOKEN", "")
    if not base.startswith("https://"): raise ValueError("ASTRA_CLOUD_URL must use HTTPS")
    if not secret: raise ValueError("ASTRA_CLOUD_TOKEN is required")
    body=json.dumps({"record_id":record_id,"decision":decision,"reviewer":reviewer},ensure_ascii=False).encode("utf-8")
    req=urllib.request.Request(base+"/v1/knowledge/review",data=body,
      headers={"Authorization":"Bearer "+secret,"Content-Type":"application/json"},method="POST")
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener=urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req,timeout=timeout) as response:
            payload=json.loads(response.read(8_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read(2_000).decode("utf-8",errors="replace")
        raise RuntimeError(f"ASTRA cloud returned HTTP {exc.code}: {detail}") from exc
    if not payload.get("ok"): raise RuntimeError("Knowledge item was not pending or could not be reviewed")
    return payload


def search_remote_knowledge(query: str, engine: str | None = None, status: str = "approved",
                            base_url: str | None = None, token: str | None = None, timeout: int = 30) -> dict:
    """Retrieve approved knowledge from the personal cloud for an engine."""
    if status not in {"pending","approved","rejected","all"}: raise ValueError("invalid status")
    base=(base_url or os.environ.get("ASTRA_CLOUD_URL", "")).rstrip("/")
    secret=token or os.environ.get("ASTRA_CLOUD_TOKEN", "")
    if not base.startswith("https://"): raise ValueError("ASTRA_CLOUD_URL must use HTTPS")
    if not secret: raise ValueError("ASTRA_CLOUD_TOKEN is required")
    from urllib.parse import urlencode
    params={"q":query,"status":status}
    if engine: params["engine"]=engine.upper()
    req=urllib.request.Request(base+"/v1/knowledge?"+urlencode(params),headers={"Authorization":"Bearer "+secret},method="GET")
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener=urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req,timeout=timeout) as response: return json.loads(response.read(1_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=exc.read(2_000).decode("utf-8",errors="replace")
        raise RuntimeError(f"ASTRA cloud returned HTTP {exc.code}: {detail}") from exc

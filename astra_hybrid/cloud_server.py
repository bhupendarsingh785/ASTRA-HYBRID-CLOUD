"""Minimal self-hostable ASTRA knowledge/control-plane server (stdlib only).

This is not a hosted cloud deployment. It can run Piper/eSpeak inference if those binaries and voice models are installed. Deploy behind HTTPS
on the user's own VPS/home server; set ASTRA_CLOUD_TOKEN before starting.
"""
from __future__ import annotations
import hmac, json, os, shutil, subprocess, tempfile, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .knowledge_hub import list_records, submit, review, search_records

class Handler(BaseHTTPRequestHandler):
    server_version = "ASTRA-Hybrid/26"
    _tts_slots = threading.BoundedSemaphore(2)
    def _send(self, code: int, payload: dict):
        data=json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code); self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def _authorized(self):
        expected=os.environ.get("ASTRA_CLOUD_TOKEN", "")
        supplied=self.headers.get("Authorization", "")
        if supplied.startswith("Bearer "): supplied=supplied[7:]
        return bool(expected) and hmac.compare_digest(expected, supplied)
    def do_GET(self):
        if self.path == "/health": return self._send(200,{"ok":True,"service":"astra-hybrid-cloud","tts_engines":["AGNI","VAYU"]})
        if not self._authorized(): return self._send(401,{"ok":False,"error":"unauthorized"})
        if self.path == "/v1/knowledge" or self.path.startswith("/v1/knowledge?"):
            from urllib.parse import urlsplit, parse_qs
            q=parse_qs(urlsplit(self.path).query)
            status=q.get("status",["pending"])[0]; engine=q.get("engine",[None])[0]; term=q.get("q",[None])[0]
            if status not in {"pending","approved","rejected","all"}: return self._send(400,{"ok":False,"error":"invalid_status"})
            rows=search_records(term,engine,status,50) if term else list_records(status,engine)[:500]
            return self._send(200,{"ok":True,"count":len(rows),"records":rows})
        return self._send(404,{"ok":False,"error":"not_found"})
    def do_POST(self):
        if not self._authorized(): return self._send(401,{"ok":False,"error":"unauthorized"})
        if self.path == "/v1/tts":
            if not self._tts_slots.acquire(blocking=False): return self._send(429,{"ok":False,"error":"tts_capacity_busy"})
            try: return self._render_tts()
            finally: self._tts_slots.release()
        if self.path == "/v1/knowledge/review":
            try:
                n=int(self.headers.get("Content-Length","0"))
                if n<1 or n>8_000: return self._send(413,{"ok":False,"error":"invalid_body_size"})
                body=json.loads(self.rfile.read(n).decode("utf-8"))
                ok=review(str(body["record_id"]),str(body["decision"]),str(body.get("reviewer","owner")))
                return self._send(200 if ok else 409,{"ok":ok,"status":body.get("decision") if ok else "not_pending"})
            except Exception as exc: return self._send(400,{"ok":False,"error":type(exc).__name__})
        if self.path != "/v1/knowledge/submit": return self._send(404,{"ok":False,"error":"not_found"})
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<1 or n>250_000: return self._send(413,{"ok":False,"error":"invalid_body_size"})
            body=json.loads(self.rfile.read(n).decode("utf-8"))
            rid=submit(body["source_type"],body["source_id"],body["target_engine"],body["topic"],body["content"],body.get("metadata",{}))
            return self._send(202,{"ok":True,"record_id":rid,"status":"pending_review"})
        except Exception as exc:
            return self._send(400,{"ok":False,"error":str(exc)})
    def _render_tts(self):
        """Remote execution of the user's own Piper/eSpeak installation only."""
        temp_path = None
        try:
            n=int(self.headers.get("Content-Length","0"))
            if n<1 or n>40_000: return self._send(413,{"ok":False,"error":"invalid_body_size"})
            body=json.loads(self.rfile.read(n).decode("utf-8"))
            engine=str(body.get("engine", "")).upper()
            text=str(body.get("text", ""))
            if engine not in {"AGNI", "VAYU"}: return self._send(400,{"ok":False,"error":"only AGNI/PIPER and VAYU/ESPEAK are enabled on this cloud worker"})
            if not text.strip() or len(text)>8000: return self._send(400,{"ok":False,"error":"text must be 1..8000 characters"})
            fd, temp_path = tempfile.mkstemp(suffix=".wav"); os.close(fd)
            if engine == "AGNI":
                python=os.environ.get("PYTHON","python3"); model=os.environ.get("PIPER_MODEL_PATH", "")
                if not shutil.which(python) or not model or not Path(model).is_file() or not Path(model+".json").is_file():
                    return self._send(503,{"ok":False,"error":"cloud Python, piper-tts package, PIPER_MODEL_PATH .onnx and matching .onnx.json config are required"})
                cmd=[python,"-m","piper","-m",model,"-f",temp_path,"--",text]
                subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=True)
            else:
                binary=shutil.which("espeak-ng")
                if not binary: return self._send(503,{"ok":False,"error":"cloud espeak-ng is not installed"})
                subprocess.run([binary,"-v", "hi", "-w", temp_path, text],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,check=True)
            audio=Path(temp_path).read_bytes()
            if len(audio)<1000 or not audio.startswith(b"RIFF"):
                return self._send(502,{"ok":False,"error":"TTS backend returned invalid WAV"})
            self.send_response(200); self.send_header("Content-Type","audio/wav")
            self.send_header("Content-Length",str(len(audio))); self.send_header("X-ASTRA-Engine",engine)
            self.end_headers(); self.wfile.write(audio)
        except subprocess.TimeoutExpired:
            self._send(504,{"ok":False,"error":"TTS backend timeout"})
        except Exception as exc:
            self._send(502,{"ok":False,"error":f"TTS backend failed: {type(exc).__name__}"})
        finally:
            if temp_path:
                try: os.unlink(temp_path)
                except OSError: pass
    def log_message(self, fmt, *args):
        # Avoid logging authorization headers or submitted text.
        return

def main():
    host=os.environ.get("ASTRA_CLOUD_HOST","127.0.0.1")
    port=int(os.environ.get("ASTRA_CLOUD_PORT","8765"))
    token=os.environ.get("ASTRA_CLOUD_TOKEN","")
    if len(token) < 32:
        raise SystemExit("Set ASTRA_CLOUD_TOKEN to a random secret of at least 32 characters")
    if host not in {"127.0.0.1","localhost","::1"} and os.environ.get("ASTRA_CLOUD_ALLOW_PUBLIC_BIND") != "1":
        raise SystemExit("Public bind blocked. Keep loopback bind and use a hardened HTTPS reverse proxy; set ASTRA_CLOUD_ALLOW_PUBLIC_BIND=1 only for a reviewed private deployment.")
    server=ThreadingHTTPServer((host,port),Handler)
    print(f"ASTRA control-plane listening on {host}:{port}; put HTTPS reverse proxy in front before internet exposure")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__ == "__main__": main()

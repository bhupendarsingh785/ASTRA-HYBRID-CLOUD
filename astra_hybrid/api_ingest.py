"""Allowlisted, read-only JSON API ingestion into the reviewed knowledge inbox.

Security note: DNS checks here reject non-public destinations, but a production
VPS must ALSO enforce outbound network policy/firewall rules. urllib performs
its own DNS lookup at connect time, so this module alone cannot defeat every
DNS-rebinding race (see the bundled security note).
"""
from __future__ import annotations
import ipaddress, json, os, socket, urllib.parse, urllib.request
from pathlib import Path
from typing import Any
from .knowledge_hub import submit

MAX_RESPONSE_BYTES = 2_000_000
ALLOWED_AUTH_HEADERS = {"authorization", "x-api-key", "ocp-apim-subscription-key"}

def _validate_public_host(host: str) -> None:
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError("API host DNS lookup failed") from exc
        addresses = []
        for answer in answers:
            try: addresses.append(ipaddress.ip_address(answer[4][0].split("%", 1)[0]))
            except ValueError: raise ValueError("API host returned an invalid IP address")
    if not addresses:
        raise ValueError("API host did not resolve")
    if any(not ip.is_global for ip in addresses):
        raise ValueError("API host resolves to a non-public IP; blocked to prevent SSRF")

def ingest(source: dict[str, Any], target_engine: str = "ALL", environ: dict[str, str] | None = None,
           db: str | Path | None = None, timeout: int = 15) -> dict[str, Any]:
    if not source.get("enabled"): raise ValueError("API source is disabled")
    if source.get("kind") != "rest_json_get": raise ValueError("only read-only rest_json_get is supported")
    base = source.get("base_url", "")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("a credential-free HTTPS base_url without query/fragment is required")
    if parts.port not in (None, 443): raise ValueError("only HTTPS port 443 is allowed")
    allowed = {str(h).lower().rstrip(".") for h in source.get("allowed_hosts", [])}
    host = parts.hostname.lower().rstrip(".")
    if host not in allowed: raise ValueError("base URL host is not allowlisted")
    path = str(source.get("path", ""))
    if path.startswith("//") or urllib.parse.urlsplit(path).scheme or "\\" in path:
        raise ValueError("API path must be a relative path on the allowlisted host")
    url = urllib.parse.urljoin(base.rstrip("/") + "/", path)
    final = urllib.parse.urlsplit(url)
    if final.scheme != "https" or not final.hostname or final.hostname.lower().rstrip(".") not in allowed or final.port not in (None,443):
        raise ValueError("resolved URL escaped the HTTPS host allowlist")
    _validate_public_host(final.hostname)
    env = os.environ if environ is None else environ
    headers = {"Accept":"application/json", "User-Agent":"ASTRA-Hybrid-Learning/26.0"}
    auth_env = source.get("auth_env"); auth_header = str(source.get("auth_header", "Authorization"))
    if auth_env:
        if auth_header.lower() not in ALLOWED_AUTH_HEADERS or "\r" in auth_header or "\n" in auth_header:
            raise ValueError("unsupported or unsafe API authentication header")
        secret = env.get(auth_env)
        if not secret: raise ValueError(f"missing secret environment variable: {auth_env}")
        headers[auth_header] = secret
    max_bytes = min(max(int(source.get("max_bytes", 500_000)), 1), MAX_RESPONSE_BYTES)
    req = urllib.request.Request(url, headers=headers, method="GET")
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl): return None
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=min(max(float(timeout),1),30)) as response:
        content_type = response.headers.get("Content-Type", "").split(";",1)[0].strip().lower()
        if content_type != "application/json": raise ValueError("API source must return application/json")
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes: raise ValueError("API response exceeded max_bytes")
    payload = json.loads(raw.decode("utf-8"))
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    kwargs = {"source_type":"api", "source_id":str(source["id"]), "target_engine":target_engine,
              "topic":str(source.get("purpose", "API evidence")), "content":content,
              "metadata":{"url":url,"method":"GET","review_required":True,"content_type":"application/json"}}
    if db is not None: kwargs["db"] = db
    rid = submit(**kwargs)
    return {"ok":True,"record_id":rid,"status":"pending_review","bytes":len(raw),
            "note":"API data stored as evidence only; it does not train models or change code."}

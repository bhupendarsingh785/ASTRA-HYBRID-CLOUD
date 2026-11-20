"""Resolve local/cloud execution policy without pretending providers are interchangeable."""
from __future__ import annotations
import json, os, shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "engine_modes.json"

def load_config(path: str | Path = CONFIG) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _local_ready(engine: str, spec: dict[str, Any], environ: dict[str, str]) -> tuple[bool, str]:
    provider = spec.get("provider")
    if provider == "piper":
        python = environ.get("PYTHON", "python")
        python_ok = bool(shutil.which(python))
        try:
            import importlib.util
            package_ok = importlib.util.find_spec("piper") is not None
        except Exception:
            package_ok = False
        model = environ.get("PIPER_MODEL_PATH", "")
        model_ok = bool(model) and Path(model).is_file() and Path(model).suffix.lower() == ".onnx" and Path(model+".json").is_file()
        if not python_ok: return False, "Python executable missing"
        if not package_ok: return False, "Install the maintained piper-tts package (CLI: python -m piper)"
        return (True, "Piper Python package and ONNX model/config found; run a real audio smoke test") if model_ok else (False, "Set PIPER_MODEL_PATH to a Hindi .onnx model with its matching .onnx.json config")
    if provider == "espeak_ng":
        ok = bool(shutil.which("espeak-ng"))
        return ok, "espeak-ng found" if ok else "espeak-ng missing"
    if provider == "indic_tiny_tts":
        if environ.get("ASTRA_ALLOW_TINY_TTS_REMOTE_CODE") != "1":
            return False, "Review pinned upstream model code and explicitly set ASTRA_ALLOW_TINY_TTS_REMOTE_CODE=1"
        model_dir = environ.get("ASTRA_INDIC_TINY_TTS_MODEL_DIR", "")
        p = Path(model_dir) if model_dir else None
        has_weights = bool(p and p.is_dir() and any((p / name).is_file() for name in ("model.onnx", "model.safetensors", "pytorch_model.bin")))
        if not has_weights:
            return False, "Pinned Hindi model weights not found; set ASTRA_INDIC_TINY_TTS_MODEL_DIR after reviewing and installing the model"
        try:
            import torch  # noqa: F401
            import soundfile  # noqa: F401
            return True, "Model weights and Python runtime dependencies found; run a real audio smoke test"
        except Exception:
            return False, "Model weights found but runtime dependencies are missing"
    if provider == "personal_local_adapter":
        raw = environ.get("ASTRA_LOCAL_TTS_COMMAND", "")
        if not raw: return False, "Set ASTRA_LOCAL_TTS_COMMAND to your reviewed personal local model adapter"
        try:
            command = json.loads(raw)
            if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
                return False, "ASTRA_LOCAL_TTS_COMMAND must be a JSON string array"
            if not any("{text_file}" in x for x in command) or not any("{output_file}" in x for x in command):
                return False, "Adapter must include {text_file} and {output_file} placeholders"
            executable = command[0]
            if not (Path(executable).is_file() or shutil.which(executable)):
                return False, "Configured personal adapter executable not found"
            return True, "Personal local adapter command is configured; run a real audio smoke test"
        except Exception:
            return False, "ASTRA_LOCAL_TTS_COMMAND is invalid JSON"
    return False, f"Unknown local provider: {provider}"

def _online_ready(spec: dict[str, Any], environ: dict[str, str]) -> tuple[bool, str]:
    provider = spec.get("provider")
    if provider == "edge_tts":
        try:
            import edge_tts  # noqa: F401
            return True, "edge-tts package present; live network connectivity not verified"
        except Exception:
            return False, "Install edge-tts; online connectivity will still need a live check"
    if provider == "elevenlabs_api":
        missing = [k for k in spec.get("requires_env", []) if not environ.get(k)]
        return (False, "Missing configuration: " + ", ".join(missing)) if missing else (True, "ElevenLabs API key and voice ID configured; live request not verified")
    missing = [k for k in spec.get("requires_env", []) if not environ.get(k)]
    if missing:
        return False, "Missing configuration: " + ", ".join(missing)
    if provider == "astra_personal_cloud" and not environ.get("ASTRA_CLOUD_URL", "").startswith("https://"):
        return False, "ASTRA_CLOUD_URL must be an HTTPS URL"
    return True, "Online credentials/endpoint configured; live connectivity not yet verified"

def resolve(engine: str, mode: str = "auto", environ: dict[str, str] | None = None,
            config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a truthful route plan. Does not run TTS or claim a cloud is deployed."""
    env = os.environ if environ is None else environ
    cfg = config or load_config()
    key = engine.upper()
    if key not in cfg["engines"]:
        raise ValueError(f"Unknown engine: {engine}")
    if mode not in {"auto", "local", "online"}:
        raise ValueError("mode must be auto, local, or online")
    entry = cfg["engines"][key]
    local_ok, local_note = _local_ready(key, entry["local"], env)
    online_ok, online_note = _online_ready(entry["online"], env)
    checks = {"local": (local_ok, local_note), "online": (online_ok, online_note)}
    candidates = [mode] if mode != "auto" else entry.get("fallback_order", ["local", "online"])
    chosen = next((name for name in candidates if checks[name][0]), None)
    return {
        "engine": key, "base_engine": entry["base_engine"], "requested_mode": mode,
        "selected_mode": chosen, "provider": entry[chosen]["provider"] if chosen else None,
        "ready": chosen is not None,
        "fallback_available": [n for n in ("local", "online") if n != chosen and checks[n][0]],
        "checks": {n: {"ready": checks[n][0], "detail": checks[n][1]} for n in ("local", "online")},
        "important": "A local provider is an independent voice backend, not a copy of a proprietary online voice."
    }

def status() -> dict[str, Any]:
    return {name: resolve(name) for name in load_config()["engines"]}

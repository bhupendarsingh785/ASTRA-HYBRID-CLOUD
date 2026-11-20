"""Human-reviewed voice quality feedback for iterative improvement; never trains automatically."""
from __future__ import annotations
import hashlib, json, sqlite3, time
from pathlib import Path
from typing import Any
from .knowledge_hub import DEFAULT_DB

VALID_ENGINES={"VAJRA","AGNI","VAYU","ASTRA"}
SCORES=("naturalness","pronunciation","fluency","emotion","character_consistency")

def record(engine: str, sample_id: str, audio_path: str | Path, scores: dict[str,int],
           notes: str="", model_version: str="unknown", consent_to_training: bool=False,
           db: str | Path=DEFAULT_DB) -> str:
    key=engine.upper(); p=Path(audio_path)
    if key not in VALID_ENGINES: raise ValueError("unknown engine")
    if not p.is_file(): raise ValueError("audio sample does not exist")
    if set(scores)!=set(SCORES) or any(type(v) is not int or not 1<=v<=5 for v in scores.values()):
        raise ValueError("all five quality scores must be integers from 1 to 5")
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    rid=hashlib.sha256(f"{key}|{sample_id}|{digest}|{model_version}".encode()).hexdigest()[:24]
    path=Path(db); path.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE IF NOT EXISTS voice_quality_feedback (id TEXT PRIMARY KEY, engine TEXT, sample_id TEXT, audio_sha256 TEXT, model_version TEXT, scores_json TEXT, notes TEXT, consent_to_training INTEGER, created_at INTEGER)")
        c.execute("INSERT OR IGNORE INTO voice_quality_feedback VALUES (?,?,?,?,?,?,?,?,?)",
          (rid,key,sample_id,digest,model_version,json.dumps(scores,sort_keys=True),notes[:2000],int(consent_to_training),int(time.time())))
    return rid

def report(engine: str | None=None, db: str | Path=DEFAULT_DB) -> dict[str,Any]:
    path=Path(db)
    if not path.exists(): return {"count":0,"engines":{}}
    with sqlite3.connect(path) as c:
        c.row_factory=sqlite3.Row
        rows=c.execute("SELECT engine,scores_json,consent_to_training FROM voice_quality_feedback"+(" WHERE engine=?" if engine else ""),((engine.upper(),) if engine else ())).fetchall()
    grouped={}
    for row in rows:
        g=grouped.setdefault(row['engine'],{"count":0,"scores":{k:0 for k in SCORES},"training_consented":0})
        scores=json.loads(row['scores_json']); g['count']+=1
        for k,v in scores.items(): g['scores'][k]+=v
        g['training_consented']+=row['consent_to_training']
    for g in grouped.values(): g['scores']={k:round(v/g['count'],2) for k,v in g['scores'].items()}
    return {"count":len(rows),"engines":grouped,"note":"Human feedback summary only; no model weights or code were changed."}

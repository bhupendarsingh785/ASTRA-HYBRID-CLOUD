"""SQLite knowledge inbox: browser/API/agent knowledge is pending until reviewed."""
from __future__ import annotations
import hashlib, json, os, sqlite3, time
from pathlib import Path
from typing import Any

DEFAULT_DB = Path(os.environ.get("ASTRA_KNOWLEDGE_DB", str(Path(__file__).resolve().parent / "data" / "knowledge_hub.sqlite3")))

def _connect(db: str | Path = DEFAULT_DB):
    p = Path(db); p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p); c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS knowledge (
      id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_id TEXT NOT NULL,
      target_engine TEXT NOT NULL, topic TEXT NOT NULL, content TEXT NOT NULL,
      content_sha256 TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
      created_at INTEGER NOT NULL, reviewed_at INTEGER, reviewer TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}')""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge(status, target_engine)")
    c.commit(); return c

def submit(source_type: str, source_id: str, target_engine: str, topic: str,
           content: str, metadata: dict[str, Any] | None = None, db: str | Path = DEFAULT_DB) -> str:
    if source_type not in {"browser", "api", "agent", "human", "benchmark"}:
        raise ValueError("unsupported source_type")
    if target_engine.upper() not in {"VAJRA", "AGNI", "VAYU", "ASTRA", "ALL"}:
        raise ValueError("unknown target engine")
    if not content.strip() or len(content) > 200_000:
        raise ValueError("content must be 1..200000 characters")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    record_id = hashlib.sha256(f"{source_type}|{source_id}|{target_engine}|{topic}|{digest}".encode()).hexdigest()[:24]
    with _connect(db) as c:
        c.execute("INSERT OR IGNORE INTO knowledge(id,source_type,source_id,target_engine,topic,content,content_sha256,created_at,metadata_json) VALUES(?,?,?,?,?,?,?,?,?)",
          (record_id, source_type, source_id, target_engine.upper(), topic, content, digest, int(time.time()), json.dumps(metadata or {}, ensure_ascii=False)))
    return record_id

def list_records(status: str = "pending", engine: str | None = None, db: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    if status not in {"pending", "approved", "rejected", "all"}: raise ValueError("invalid status")
    sql = "SELECT * FROM knowledge"; args: list[Any] = []; where=[]
    if status != "all": where.append("status=?"); args.append(status)
    if engine: where.append("(target_engine=? OR target_engine='ALL')"); args.append(engine.upper())
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC"
    with _connect(db) as c: return [dict(r) for r in c.execute(sql, args).fetchall()]

def review(record_id: str, decision: str, reviewer: str, db: str | Path = DEFAULT_DB) -> bool:
    if decision not in {"approved", "rejected"}: raise ValueError("decision must be approved/rejected")
    with _connect(db) as c:
        cur = c.execute("UPDATE knowledge SET status=?, reviewed_at=?, reviewer=? WHERE id=? AND status='pending'",
                        (decision, int(time.time()), reviewer, record_id))
        return cur.rowcount == 1

def propose_agent_exchange(from_agent: str, to_engine: str, topic: str, content: str,
                           db: str | Path = DEFAULT_DB) -> str:
    """Agent-to-agent sharing is a proposal; it never writes directly to another agent's memory."""
    return submit("agent", from_agent, to_engine, topic, content,
                  {"exchange": "proposal_only", "requires_human_review": True}, db)


def search_records(query: str, engine: str | None = None, status: str = "approved",
                   limit: int = 20, db: str | Path = DEFAULT_DB) -> list[dict[str, Any]]:
    """Retrieve reviewed knowledge for an engine; pending evidence is excluded by default."""
    term=query.strip()
    if not term or len(term)>200: raise ValueError("query must be 1..200 characters")
    if status not in {"pending","approved","rejected","all"}: raise ValueError("invalid status")
    limit=min(max(int(limit),1),50)
    clauses=[]; args=[]
    if status!="all": clauses.append("status=?"); args.append(status)
    if engine: clauses.append("(target_engine=? OR target_engine='ALL')"); args.append(engine.upper())
    clauses.append("(topic LIKE ? OR content LIKE ? OR source_id LIKE ?)")
    like="%"+term+"%"; args.extend([like,like,like])
    sql="SELECT * FROM knowledge WHERE "+" AND ".join(clauses)+" ORDER BY created_at DESC LIMIT ?"; args.append(limit)
    with _connect(db) as c: return [dict(r) for r in c.execute(sql,args).fetchall()]

"""ASTRA Hybrid command line."""
from __future__ import annotations
import argparse, json
from .hybrid_router import status, resolve
from .tts_runtime import synthesize
from .quality_feedback import report

def main():
    p=argparse.ArgumentParser(prog="astra-hybrid")
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("status")
    r=sub.add_parser("route"); r.add_argument("engine"); r.add_argument("--mode",choices=("auto","local","online"),default="auto")
    t=sub.add_parser("speak"); t.add_argument("engine"); t.add_argument("text"); t.add_argument("--out",required=True); t.add_argument("--mode",choices=("auto","local","online"),default="auto")
    q=sub.add_parser("quality-report"); q.add_argument("--engine")
    k=sub.add_parser("review-knowledge"); k.add_argument("record_id"); k.add_argument("decision",choices=("approved","rejected")); k.add_argument("--reviewer",default="owner"); k.add_argument("--cloud",action="store_true")
    s=sub.add_parser("knowledge-search"); s.add_argument("query"); s.add_argument("--engine"); s.add_argument("--status",choices=("approved","pending","rejected","all"),default="approved"); s.add_argument("--cloud",action="store_true")
    a=p.parse_args()
    if a.cmd=="status": result=status()
    elif a.cmd=="route": result=resolve(a.engine,a.mode)
    elif a.cmd=="speak": result=synthesize(a.engine,a.text,a.out,a.mode)
    elif a.cmd=="review-knowledge":
        if a.cloud:
            from .cloud_client import review_remote_knowledge
            result=review_remote_knowledge(a.record_id,a.decision,a.reviewer)
        else:
            from .knowledge_hub import review
            result={"ok":review(a.record_id,a.decision,a.reviewer),"decision":a.decision}
    elif a.cmd=="knowledge-search":
        if a.cloud:
            from .cloud_client import search_remote_knowledge
            result=search_remote_knowledge(a.query,a.engine,a.status)
        else:
            from .knowledge_hub import search_records
            result={"ok":True,"records":search_records(a.query,a.engine,a.status)}
    else: result=report(a.engine)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()

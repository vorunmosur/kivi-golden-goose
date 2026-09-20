"""Model-backed challenge runner with independent keys and complete DB exports.

python -m eval.run_longitudinal --output eval/longitudinal-initial
An output directory is write-once. --limit visibly produces a partial run.
"""
import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path
from eval.longitudinal_cases import build


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf8", newline="\n")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--scenario", type=int, choices=range(10))
    args=parser.parse_args()
    out=Path(args.output)
    if out.exists(): raise SystemExit("Use a fresh output directory")
    out.mkdir(parents=True)
    import subprocess
    code_manifest={"started_at":__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
                   "head":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
                   "dirty_tracked_paths":subprocess.check_output(["git","diff","--name-only"],text=True).splitlines(),
                   "source_sha256_lf_normalized":{str(p):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for folder in ["app","eval","alembic"] for p in Path(folder).rglob("*.py")}}
    dump(out/"code_manifest.json",code_manifest)
    os.environ["KIVI_DB_PATH"]=str(out/"memory.db")
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.main import app
    from app.config import settings
    from app.db import SessionLocal
    from app.models import Memory, Interaction, MemorySource, MemoryDecision, QueryTrace, Entity, EntityAlias, ForgetBoundary
    if settings.provider_kind!="ollama": raise SystemExit("KIVI_PROVIDER=ollama required")
    cases, checks=build()
    scenarios=set(range(10)) if args.scenario is None else {args.scenario}
    cases=[c for c in cases if c["scenario"] in scenarios]
    checks=[q for q in checks if q["scenario"] in scenarios]
    cases=cases[:args.limit]
    dump(out/"expected.json",{"cases":cases,"queries":checks})
    (out/"inputs.jsonl").write_text("".join(json.dumps(c["record"])+"\n" for c in cases),encoding="utf8",newline="\n")
    ingestion, queries, states, ids=[],[],[],{}
    def append(filename, entry):
        with (out/filename).open("a",encoding="utf8",newline="\n") as stream: stream.write(json.dumps(entry,default=str)+"\n")
    def rows(db): return list(db.scalars(select(Memory)))
    with TestClient(app,raise_server_exceptions=False) as client:
        for c in cases:
            idx=c["step"]*10+c["scenario"]
            started=time.perf_counter()
            response=client.post("/api/import",files={"file":("record.json",json.dumps([c["record"]]),"application/json")})
            try: data=response.json()
            except ValueError: data={"error":response.text}
            entries=data.get("results",[])
            if entries: ids[idx]=entries[0].get("interaction_id")
            with SessionLocal() as db:
                links=list(db.scalars(select(MemorySource).where(MemorySource.interaction_id==ids.get(idx,-1))))
                retained=bool(links)
            expected=c["admission"]
            passed=(retained if expected=="retain" else not retained if expected=="reject" else None)
            entry={"index":idx,"scenario":c["scenario"],"step":c["step"],"status":response.status_code,
                   "result":data,"retained":retained,"admission_passed":passed,"latency_ms":(time.perf_counter()-started)*1000}
            ingestion.append(entry);append("ingestion.jsonl",entry)
            print(json.dumps({"index":idx,"failed":data.get("failed"),"admission_passed":passed,"ms":round(entry["latency_ms"])}),flush=True)
            # State checks use source identity, status and literal values, not extractor predicates.
            checkpoint=c["scenario"]==max(scenarios)
            if checkpoint and c["step"] in {2,9,10,15,17,22,49}:
                step=c["step"]
                from eval.longitudinal_cases import WORLDS
                with SessionLocal() as db:
                    memories=rows(db)
                    for w,(project,old,possible,new,*_) in enumerate(WORLDS):
                        if w not in scenarios: continue
                        def has_source(m,s): return any(x.interaction_id==ids.get(s*10+w) for x in m.sources)
                        def endpoint(m,name): return name.casefold() in (m.subject+" "+m.value).casefold()
                        if step==2:
                            passed=any(endpoint(m,old) and m.status=="active" and has_source(m,1) for m in memories) and not any(endpoint(m,possible) and m.status=="active" and has_source(m,2) for m in memories)
                            name="tentative_does_not_replace"
                        elif step==9:
                            passed=any(endpoint(m,new) and m.status=="active" and has_source(m,9) for m in memories) and not any(m.status=="active" and has_source(m,1) for m in memories)
                            name="confirmed_replacement"
                        elif step in {10,15,17}:
                            target={10:10,15:10,17:17}[step]
                            candidates=[m for m in memories if has_source(m,target)]
                            passed=any(m.status=="active" for m in candidates) if step!=15 else bool(candidates) and all(m.status=="deleted" for m in candidates)
                            name={10:"deadline_correction",15:"forget_all_versions",17:"relearn_after_boundary"}[step]
                        elif step==22:
                            candidates=[m for m in memories if any(has_source(m,s) for s in [20,21,22]) and m.memory_type=="preference"]
                            passed=bool(candidates) and all(m.explicitness=="inferred" and m.scope!="global" for m in candidates)
                            name="behavioral_preference_conservative"
                        else:
                            candidates=[m for m in memories if has_source(m,14)]
                            passed=all(m.status!="active" for m in candidates)
                            name="temporary_not_current"
                        states.append({"after":idx,"scenario":w,"name":name,"passed":bool(passed)})
                dump(out/"state_checks.json",states)
            for check in [q for q in checks if checkpoint and q["after"]//10==c["step"]]:
                started=time.perf_counter()
                response=client.post("/api/hey-kivi",json={"query":check["query"],"current_context":check["context"]})
                try: result=response.json()
                except ValueError: result={"error":response.text}
                answer=result.get("response","").casefold()
                abstained="don\u2019t know" in answer or "don't know" in answer or "do not know" in answer
                required=all(x.casefold() in answer for x in check["required"])
                no_leak=all(x.casefold() not in answer for x in check["forbidden"])
                kind=check["kind"]
                passed=required and no_leak and bool(answer) and response.status_code==200
                if kind in {"unsupported","non_retention","forget_leakage","expiry"}: passed=passed and abstained
                if kind=="entity_ambiguity": passed=passed and "which" in answer and "alex" in answer
                with SessionLocal() as db:
                    trace=db.get(QueryTrace,result.get("trace_id",-1))
                    candidate_ids=json.loads(trace.context_json).get("candidate_memory_ids",[]) if trace else []
                    source_ids={s.interaction_id for m in rows(db) if m.id in candidate_ids for s in m.sources}
                    source_ids.update(h["interaction_id"] for h in result.get("history_evidence",[]))
                    wanted={ids[s] for s in check["sources"] if s in ids}
                    recall=len(wanted & source_ids)/len(wanted) if wanted else None
                prefs=[m for m in result.get("memories",[]) if m["type"]=="preference"]
                if kind=="personal_scope": passed=passed and not prefs
                if kind=="scoped_preference": passed=passed and any("detailed" in m["value"].casefold() for m in prefs) and not any("concise" in m["value"].casefold() for m in prefs)
                entry={"check":check,"status":response.status_code,"result":result,"passed":passed,"abstained":abstained,
                       "retrieval_source_recall":recall,"expected_source_ids":sorted(wanted),"latency_ms":(time.perf_counter()-started)*1000}
                queries.append(entry);append("queries.jsonl",entry)
                print(json.dumps({"kind":kind,"scenario":check["scenario"],"passed":passed,"recall":recall,"answer":result.get("response")}),flush=True)
        with SessionLocal() as db:
            for model in [Interaction,Memory,MemorySource,MemoryDecision,QueryTrace,Entity,EntityAlias,ForgetBoundary]:
                dump(out/f"{model.__tablename__}.json",[{col.name:getattr(r,col.name) for col in model.__table__.columns if col.name!="embedding_json"} for r in db.scalars(select(model))])
            missing=[m.id for m in rows(db) if not m.sources]
            bad_spans=[s.id for s in db.scalars(select(MemorySource)) if not s.evidence_text or s.evidence_text not in s.interaction.formatted_text and s.evidence_text not in s.interaction.raw_asr]
            secret=[m.id for m in rows(db) if "sk-synthetic" in m.canonical_text or "LOCKER" in m.value]
    def counts(values): return {"passed":sum(v is True for v in values),"cases":sum(v is not None for v in values)}
    def latency(values): return {"p50_ms":statistics.median(values),"p95_ms":sorted(values)[int(.95*(len(values)-1))]} if values else None
    usage=[]
    def collect(obj):
        if isinstance(obj,dict):
            if "prompt_tokens" in obj: usage.append(obj)
            else:
                for v in obj.values(): collect(v)
        elif isinstance(obj,list):
            for v in obj: collect(v)
    collect(ingestion);collect([q["result"].get("model_usage",{}) for q in queries])
    recalls=[q["retrieval_source_recall"] for q in queries if q["retrieval_source_recall"] is not None]
    summary={"run_kind":"full_longitudinal" if len(cases)==500 else "partial_longitudinal","records":len(cases),
             "scenarios":sorted(scenarios),"code_head":code_manifest["head"],
             "input_sha256":hashlib.sha256((out/"inputs.jsonl").read_bytes()).hexdigest(),"model":settings.llm_model,"embedding_model":settings.embedding_model,
             "ingestion_failures":sum(e["status"]!=200 or bool(e["result"].get("failed")) for e in ingestion),
             "admission":counts([e["admission_passed"] for e in ingestion]),"state":counts([s["passed"] for s in states]),
             "queries":counts([q["passed"] for q in queries]),"query_categories":{kind:counts([q["passed"] for q in queries if q["check"]["kind"]==kind]) for kind in sorted({q["check"]["kind"] for q in queries})},
             "retrieval_mean_source_recall":statistics.mean(recalls) if recalls else None,"retrieval_hit_rate":statistics.mean(r>0 for r in recalls) if recalls else None,
             "missing_provenance":missing,"invalid_evidence_spans":bad_spans,"secret_memories":secret,
             "ingestion_latency":latency([e["latency_ms"] for e in ingestion]),"query_latency":latency([q["latency_ms"] for q in queries]),
             "model_calls":len(usage),"prompt_tokens":sum(u.get("prompt_tokens",0) for u in usage),"completion_tokens":sum(u.get("completion_tokens",0) for u in usage),
             "database_bytes":sum(p.stat().st_size for p in out.glob("memory.db*")),"provider_spend_usd":0,
             "limitations":["Synthetic template coverage, not natural traffic accuracy","Literal independent answer keys and source recall are proxies, not a proof of every generated claim","Inspect-kind observations are not scored for admission","Embeddings calls excluded from chat-token totals"]}
    from eval.semantic_diagnostics import audit
    summary["semantic_diagnostics"]=audit(out)
    dump(out/"summary.json",summary);print(json.dumps(summary),flush=True)
    if summary["semantic_diagnostics"]["passed"]!=summary["semantic_diagnostics"]["cases"] or summary["ingestion_failures"] or secret or missing or bad_spans or any(e["admission_passed"] is False for e in ingestion) or any(not s["passed"] for s in states) or any(not q["passed"] for q in queries): raise SystemExit(1)


if __name__=="__main__": main()

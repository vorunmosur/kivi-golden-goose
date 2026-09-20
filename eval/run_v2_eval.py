"""Live end-to-end evaluator; no injected candidates or prepared answers.
Usage: python -m eval.run_v2_eval [--corpus data/dev_corpus.jsonl] [--limit N]
Always uses a separate database. Partial runs are visibly labeled.
"""
import argparse,json,os,time,statistics,hashlib
from pathlib import Path
from datetime import datetime,timedelta,timezone
parser=argparse.ArgumentParser();parser.add_argument("--corpus");parser.add_argument("--limit",type=int);parser.add_argument("--output",default="eval/v2_live")
args=parser.parse_args()
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
os.environ["KIVI_DB_PATH"]=str(out/"memory.db")
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.db import SessionLocal
from app.models import Memory,MemoryDecision,MemorySource
from sqlalchemy import select
if settings.provider_kind!="ollama": raise SystemExit("Set KIVI_PROVIDER=ollama. This evaluation must use a real model.")
base=datetime(2026,9,1,9,tzinfo=timezone.utc)
pilot=[
    "Rajeev is my manager.",
    "Priya might become my manager next month.",
    "Golden Goose is my current project.",
    "Aaditya reviews Golden Goose. We call Aaditya Aadi.",
    "Golden Goose uses FastAPI for its backend.",
    "Golden Goose is due September 20, 2026.",
    "Keep my work emails concise.",
    "For client emails at work, I prefer detailed explanations.",
    "Spent this afternoon debugging the auth middleware invalidating refreshed tokens for Golden Goose.",
    "Actually Priya officially took over as my manager today.",
    "My API key is sk-abcdefghijklmnop.",
    "Don't remember this: my hotel room is 804.",
    "The exhibition curator is Leela. Leela is organizing the ceramics exhibition.",
    "For the ceramics exhibition we need stoneware labels by September 25, 2026.",
    "Forget who my manager is.",
    "Ananya is now my manager.",
]
records=[{"raw_asr":text.lower(),"formatted_output":text,"timestamp":(base+timedelta(hours=i)).isoformat(),"app":"Slack","style":"work messaging","session_id":f"day-{i//4}"} for i,text in enumerate(pilot)]
if args.corpus:
    path=Path(args.corpus)
    if path.suffix==".jsonl": records=[json.loads(line) for line in path.read_text(encoding="utf8").splitlines() if line.strip()]
    elif path.suffix==".csv":
        import csv
        records=list(csv.DictReader(path.open(encoding="utf-8-sig")))
    else:
        records=json.loads(path.read_text(encoding="utf8"));records=records if isinstance(records,list) else records["records"]
original_count=len(records)
if args.limit: records=records[:args.limit]
(out/"inputs.jsonl").write_text("".join(json.dumps(r)+"\n" for r in records),encoding="utf8")
results=[];latencies=[];queries=[];state_checks=[]

def ask(client,query,expect=None,context=None):
    started=time.perf_counter()
    response=client.post("/api/hey-kivi",json={"query":query,"current_context":context or {}})
    data=response.json();text=data.get("response","")
    passed=expect(text.casefold(),data) if expect else None
    entry={"query":query,"status":response.status_code,"result":data,"latency_ms":(time.perf_counter()-started)*1000,"passed":passed}
    queries.append(entry);(out/"queries.json").write_text(json.dumps(queries,indent=2),encoding="utf8")
    print(json.dumps({"query":query,"answer":text,"passed":passed}),flush=True)

if (out/"ingestion.jsonl").exists(): raise SystemExit("Use a fresh evaluation output directory; existing evidence will not be overwritten.")
with TestClient(app,raise_server_exceptions=False) as client:
    client.post("/api/reset")
    for index,r in enumerate(records):
        started=time.perf_counter()
        response=client.post("/api/import",files={"file":("row.json",json.dumps([r]),"application/json")})
        data=response.json();latency=(time.perf_counter()-started)*1000;latencies.append(latency)
        entry={"index":index,"input":r,"status":response.status_code,"result":data,"latency_ms":latency};results.append(entry)
        with (out/"ingestion.jsonl").open("a",encoding="utf8") as stream: stream.write(json.dumps(entry)+"\n")
        print(json.dumps({"index":index,"status":response.status_code,"failed":data.get("failed"),"latency_ms":round(latency)}),flush=True)
        if not args.corpus and index in {3,7,9,14,15}:
            with SessionLocal() as db:
                rows=list(db.scalars(select(Memory)))
                if index==3:
                    passed=any(m.subject.casefold()=="aaditya" and m.predicate in {"reviews","reviewer","review"} and "golden goose" in m.value.casefold() for m in rows) or any("golden goose" in m.subject.casefold() and m.value.casefold()=="aaditya" and "review" in m.predicate for m in rows)
                    name="Named reviewer relationship has correct endpoints"
                elif index==7:
                    prefs=[m for m in rows if m.memory_type=="preference" and m.status=="active"]
                    passed=any("concise" in m.value.casefold() and '"app": "email"' in m.scope and '"context": "work"' in m.scope and 'recipient' not in m.scope for m in prefs) and any("detailed" in m.value.casefold() and '"recipient": "client"' in m.scope for m in prefs)
                    name="General and client email preferences coexist in correct scopes"
                elif index==9:
                    passed=any(m.value.casefold()=="priya" and m.predicate=="manager" and m.status=="active" for m in rows) and not any(m.value.casefold()=="rajeev" and m.status=="active" for m in rows)
                    name="Confirmed manager replacement closes previous state"
                elif index==14:
                    passed=not any(m.predicate=="manager" and m.status!="deleted" for m in rows)
                    name="Whole-slot forget deletes current and historical manager versions"
                else:
                    passed=any(m.value.casefold()=="ananya" and m.predicate=="manager" and m.status=="active" for m in rows)
                    name="Post-forget evidence teaches new manager"
                state_checks.append({"index":index,"name":name,"passed":passed})
                (out/"state_checks.json").write_text(json.dumps(state_checks,indent=2),encoding="utf8")
                print(json.dumps(state_checks[-1]),flush=True)
        if not args.corpus and index==1:
            ask(client,"Who is my manager?",lambda t,d:"rajeev" in t and "priya" not in t)
        if not args.corpus and index==9:
            ask(client,"Who is my manager?",lambda t,d:"priya" in t and "rajeev" not in t)
        if not args.corpus and index==14:
            ask(client,"Who is my manager?",lambda t,d:"know" in t and "priya" not in t and "rajeev" not in t)
    if not args.corpus and len(records)==original_count:
        ask(client,"Who is my manager?",lambda t,d:"ananya" in t)
        ask(client,"Write Aadi a work update about Golden Goose and its backend and deadline.",lambda t,d:"fastapi" in t and ("20" in t or "twentieth" in t),{"context":"work","app":"email"})
        ask(client,"What did I say about the Golden Goose login issue?",lambda t,d:"token" in t or "middleware" in t)
        ask(client,"Who is organizing the ceramics exhibition?",lambda t,d:"leela" in t)
        ask(client,"What is my passport number?",lambda t,d:"know" in t)
        ask(client,"What is my hotel room?",lambda t,d:"know" in t and "804" not in t)
    elif args.corpus:
        # Corpus-specific answer keys are never invented by the evaluator.
        for q in ["Summarize the current projects you know about.","What communication preferences have I explicitly stated?","What is my passport number?"]:
            ask(client,q)
    for endpoint in ["memories","decisions","traces","entities"]:
        (out/f"{endpoint}.json").write_text(json.dumps(client.get("/api/"+endpoint).json(),indent=2),encoding="utf8")
with SessionLocal() as db:
    memories=list(db.scalars(select(Memory)))
    unsupported=[m.id for m in memories if not m.sources]
    secret_ids=[m.id for m in memories if "sk-" in m.canonical_text or "804" in m.value]
manifest={"run_kind":"full_corpus" if args.corpus and len(records)==original_count else "pilot" if not args.corpus and len(records)==original_count else "partial_corpus" if args.corpus else "partial_pilot",
    "corpus":args.corpus or "independent longitudinal pilot","input_sha256":hashlib.sha256((out/"inputs.jsonl").read_bytes()).hexdigest(),
    "model":settings.llm_model,"embedding_model":settings.embedding_model,"records":len(records),"available_records":original_count,
    "ingestion_failures":sum(x["status"]!=200 or bool(x["result"].get("failed")) for x in results),
    "state_check_passes":sum(x["passed"] for x in state_checks),"state_check_cases":len(state_checks),
    "query_passes":sum(x["passed"] is True for x in queries),"query_cases":len(queries),"missing_provenance":unsupported,"secret_memories":secret_ids,
    "ingestion_p50_ms":statistics.median(latencies),"ingestion_p95_ms":sorted(latencies)[int(0.95*(len(latencies)-1))],
    "database_bytes":sum(p.stat().st_size for p in out.glob("memory.db*")),"local_model_cost_usd":0,"cost_excludes":"hardware and electricity"}
(out/"summary.json").write_text(json.dumps(manifest,indent=2),encoding="utf8");print(json.dumps(manifest),flush=True)
if manifest["ingestion_failures"] or manifest["secret_memories"] or manifest["missing_provenance"] or any(q["passed"] is False for q in queries) or any(not c["passed"] for c in state_checks): raise SystemExit(1)

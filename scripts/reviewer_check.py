"""Exercise real HTTP startup/import/learn/query/provenance/control/reset.

Run in a fresh clone after install: python scripts/reviewer_check.py --output PATH
The output must be outside the source tree for a final-commit clean-clone audit.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import httpx


def main():
    p=argparse.ArgumentParser();p.add_argument("--output",required=True);args=p.parse_args()
    out=Path(args.output).resolve()
    if out.exists(): raise SystemExit("Use a new reviewer output directory")
    out.mkdir(parents=True)
    env=dict(os.environ,KIVI_PROVIDER="ollama",KIVI_DB_PATH=str(out/"review.db"))
    subprocess.run([sys.executable,"-m","alembic","upgrade","head"],env=env,check=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    log=(out/"server.log").open("w",encoding="utf8")
    flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0
    process=subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port)],env=env,stdout=log,stderr=log,creationflags=flags)
    results=[{"name":"clone_commit","passed":True,"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"clean_tracked_tree":not subprocess.check_output(["git","status","--porcelain"],text=True).strip()}]
    def save(): (out/"reviewer.json").write_text(json.dumps(results,indent=2),encoding="utf8")
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}",timeout=240) as client:
            for _ in range(60):
                try:
                    if client.get("/").status_code==200: break
                except httpx.TransportError: pass
                time.sleep(.5)
            else: raise RuntimeError("Server did not start")
            def record(name, response, passed):
                entry={"name":name,"status":response.status_code,"passed":bool(passed)}
                try: entry["result"]=response.json()
                except ValueError: entry["result"]="HTML page served" if response.status_code==200 else response.text
                results.append(entry);save();print(json.dumps({k:v for k,v in entry.items() if k!="result"}),flush=True)
                assert entry["passed"],name
            r=client.get("/");record("web_page",r,r.status_code==200 and "Hey Kivi" in r.text)
            text="Nisha is my manager."
            r=client.post("/api/import",files={"file":("seed.jsonl",json.dumps({"raw_asr":text,"formatted_output":text,"app":"Notes"}),"application/json")})
            record("model_backed_import",r,r.status_code==200 and r.json().get("processed")==1 and not r.json().get("failed"))
            r=client.post("/api/interactions",json={"raw_asr":"Dev might become my manager next year.","formatted_text":"Dev might become my manager next year.","app_context":"Slack","style_context":"unknown"})
            record("learn_tentative",r,r.status_code==200)
            r=client.post("/api/hey-kivi",json={"query":"Who is my manager?"})
            record("confirmed_beats_tentative",r,r.status_code==200 and "nisha" in r.json().get("response","").casefold() and "dev" not in r.json().get("response","").casefold())
            r=client.get("/api/memories");memories=r.json()
            current=next(m for m in memories if m["value"].casefold()=="nisha" and m["status"]=="active")
            record("inspect_memory_provenance",r,bool(current["source_evidence"]))
            source_id=current["source_interaction_ids"][0]
            r=client.get(f"/api/interactions/{source_id}");record("inspect_original_input",r,r.status_code==200 and "Nisha" in r.text)
            r=client.patch(f"/api/memories/{current['id']}",json={"value":"Ritu"});record("correct_control",r,r.status_code==200 and r.json().get("action") in {"update","supersede"})
            r=client.post("/api/hey-kivi",json={"query":"Who is my manager?"})
            record("corrected_state_used",r,r.status_code==200 and "ritu" in r.json().get("response","").casefold() and "nisha" not in r.json().get("response","").casefold())
            current=next(m for m in client.get("/api/memories").json() if m["value"].casefold()=="ritu" and m["status"]=="active")
            r=client.delete(f"/api/memories/{current['id']}");record("forget_control",r,r.status_code==200)
            r=client.post("/api/hey-kivi",json={"query":"Who was my manager Ritu?"})
            answer=r.json().get("response","").casefold();record("forget_history_exclusion",r,r.status_code==200 and "ritu" not in answer)
            for endpoint in ["decisions","traces","entities"]:
                r=client.get("/api/"+endpoint);record("inspect_"+endpoint,r,r.status_code==200 and bool(r.json()))
            r=client.post("/api/reset");record("reset",r,r.status_code==200)
            for endpoint in ["memories","entities","decisions","traces"]:
                r=client.get("/api/"+endpoint);record("reset_empty_"+endpoint,r,r.json()==[])
        # A small actual evaluator run in this clone verifies the command, model and database isolation.
        subprocess.run([sys.executable,"-m","eval.run_v2_eval","--limit","2","--output",str(out/"smoke")],env=env,check=True)
        results.append({"name":"evaluation_command","passed":True});save()
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()
        log.close()


if __name__=="__main__": main()

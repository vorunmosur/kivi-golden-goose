from __future__ import annotations

import json
import csv
import io
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db, init_db
from app.models import Interaction, Memory, MemoryDecision, MemorySource, QueryTrace, Entity, EntityAlias, ForgetBoundary, utcnow
from app.schemas import InteractionIn, MemoryPatch, QueryIn
from app.services.hey_kivi import answer_query
from app.services.memory_engine import process_interaction
from app.services.lifecycle import forget, naive, reconcile, record

app = FastAPI(title="Kivi Semantic Memory — Golden Goose")
ROOT = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.post("/api/interactions")
def ingest(payload: InteractionIn, db: Session = Depends(get_db)):
    interaction = Interaction(
        raw_asr=payload.raw_asr,
        formatted_text=payload.formatted_text,
        app_context=payload.app_context,
        style_context=payload.style_context,
        session_id=payload.session_id,
        occurred_at=naive(payload.occurred_at) or utcnow(),
        metadata_json=json.dumps(payload.metadata),
        hide_mode=payload.hide_mode,
    )
    db.add(interaction); db.commit(); db.refresh(interaction)
    result = process_interaction(db, interaction)
    if payload.hide_mode and not any(a["action"] in {"create", "update", "reinforce"} for a in result["actions"]):
        # Hide Mode has no durable transcript. The response still reports the transient decision
        # to the caller, then the interaction and its audit rows are removed together.
        db.delete(interaction)
        db.commit()
    return {"interaction_id": interaction.id, **result}


@app.post("/api/hey-kivi")
def hey_kivi(payload: QueryIn, db: Session = Depends(get_db)):
    return answer_query(db, payload.query, payload.session_id, payload.current_context)


@app.get("/api/memories")
def memories(db: Session = Depends(get_db)):
    rows = db.scalars(select(Memory).order_by(Memory.updated_at.desc())).all()
    return [{
        "id": m.id,
        "memory_type": m.memory_type,
        "subject": m.subject,
        "subject_entity_id": m.subject_entity_id,
        "predicate": m.predicate,
        "value": m.value,
        "value_entity_id": m.value_entity_id,
        "canonical_text": m.canonical_text,
        "scope": m.scope,
        "status": m.status,
        "certainty": m.certainty,
        "temporal_status": m.temporal_status,
        "valid_from": m.valid_from,
        "valid_until": m.valid_to,
        "source_evidence": [{"interaction_id":s.interaction_id,"excerpt":s.evidence_text} for s in m.sources],
        "confidence": m.confidence,
        "sensitivity": m.sensitivity,
        "source_style": m.source_style,
        "explicitness": m.explicitness,
        "expires_at": m.expires_at,
        "updated_at": m.updated_at,
        "source_interaction_ids": [s.interaction_id for s in m.sources],
    } for m in rows]


@app.patch("/api/memories/{memory_id}")
def patch_memory(memory_id: int, payload: MemoryPatch, db: Session = Depends(get_db)):
    m = db.get(Memory, memory_id)
    if not m:
        raise HTTPException(404, "Memory not found")
    text=f"Correction: {m.subject} {m.predicate} is {payload.value or m.value}."
    interaction=Interaction(raw_asr=text,formatted_text=text,app_context="Memory",style_context="other",session_id="memory-control",occurred_at=utcnow(),metadata_json="{}",retrieval_blocked=True,processing_status="complete")
    db.add(interaction);db.flush()
    candidate={"memory_type":m.memory_type,"subject":m.subject,"predicate":m.predicate,"value":payload.value or m.value,
        "canonical_text":text,"scope":payload.scope or m.scope,"confidence":1.0,"explicitness":"explicit","evidence_text":text,
        "proposed_action":"create_or_update","change_kind":"correct","cardinality":"single","certainty":"confirmed","temporal_status":"current"}
    result=reconcile(db,interaction,candidate);db.commit()
    return {"ok":True,**result}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    m=db.get(Memory,memory_id)
    if not m: raise HTTPException(404,"Memory not found")
    text=f"Forget {m.subject} {m.predicate} {m.value}."
    interaction=Interaction(raw_asr=text,formatted_text=text,app_context="Memory",style_context="other",session_id="memory-control",occurred_at=utcnow(),metadata_json="{}",retrieval_blocked=True,processing_status="complete")
    db.add(interaction);db.flush()
    result=forget(db,interaction,{"subject":m.subject,"predicate":m.predicate,"scope":m.scope,"value":m.value},True,selected_memory=m)
    db.commit();return {"ok":True,**result}


@app.get("/api/decisions")
def decisions(db: Session = Depends(get_db)):
    rows = db.scalars(select(MemoryDecision).order_by(MemoryDecision.id.desc()).limit(100)).all()
    return [{
        "id": d.id,
        "interaction_id": d.interaction_id,
        "action": d.action,
        "reason": d.reason,
        "memory_id": d.memory_id,
        "candidate": json.loads(d.candidate_json),
        "previous_state": json.loads(d.previous_state_json),
        "new_state": json.loads(d.new_state_json),
        "decision_maker": d.decision_maker,
        "created_at": d.created_at,
    } for d in rows]


@app.get("/api/traces")
def traces(db: Session = Depends(get_db)):
    rows = db.scalars(select(QueryTrace).order_by(QueryTrace.id.desc()).limit(100)).all()
    return [{
        "id": t.id,
        "context": json.loads(t.context_json),
        "query": t.query,
        "response": t.response,
        "retrieved_memory_ids": json.loads(t.retrieved_memory_ids_json),
        "source_interaction_ids": json.loads(t.source_interaction_ids_json),
        "reason": t.decision_reason,
        "retrieval_latency_ms": t.retrieval_latency_ms,
        "end_to_end_latency_ms": t.end_to_end_latency_ms,
        "model_usage": json.loads(t.model_usage_json),
        "created_at": t.created_at,
    } for t in rows]


@app.post("/api/import")
def import_corpus(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw=file.file.read().decode("utf-8-sig")
    try:
        name=(file.filename or "").lower()
        if name.endswith(".csv"): records=list(csv.DictReader(io.StringIO(raw)))
        elif name.endswith(".jsonl"): records=[json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            parsed=json.loads(raw);records=parsed if isinstance(parsed,list) else parsed["records"]
        if not isinstance(records,list): raise ValueError("Expected a record list")
    except (ValueError,KeyError,TypeError) as error: raise HTTPException(422,f"Invalid corpus: {error}")
    normalized=[];errors=[]
    for index,r in enumerate(records):
        try:
            if not isinstance(r,dict): raise ValueError("Record must be an object")
            normalized.append((index,InteractionIn.model_validate({
                "raw_asr":r["raw_asr"],"formatted_text":r.get("formatted_output") or r.get("formatted_text") or r.get("llm_formatted_output") or r["raw_asr"],
                "app_context":r.get("app_context") or r.get("app") or "other","style_context":r.get("style_context") or r.get("style") or "other",
                "session_id":r.get("session_id") or "import","occurred_at":r.get("timestamp") or r.get("occurred_at") or None,
                "hide_mode":r.get("hide_mode") or False,"metadata":r.get("metadata") if isinstance(r.get("metadata"),dict) else {"external_id":r.get("id")}})))
        except Exception as error: errors.append({"row":index,"error":str(error)})
    normalized.sort(key=lambda x:(naive(x[1].occurred_at) or utcnow(),x[0]))
    results=[]
    for index,payload in normalized:
        try:
            existing=None
            if payload.occurred_at:
                existing=db.scalar(select(Interaction).where(Interaction.raw_asr==payload.raw_asr,
                    Interaction.formatted_text==payload.formatted_text,Interaction.occurred_at==naive(payload.occurred_at),
                    Interaction.app_context==payload.app_context,Interaction.session_id==payload.session_id))
            if existing and existing.processing_status=="complete":
                results.append({"row":index,"interaction_id":existing.id,"replayed":True,"actions":[],"candidates":[],"model_usage":{}})
            elif existing:
                results.append({"row":index,"interaction_id":existing.id,**process_interaction(db,existing)})
            else: results.append({"row":index,**ingest(payload,db)})
        except Exception as error:
            db.rollback();errors.append({"row":index,"error":str(error)})
    return {"processed":len(results),"failed":len(errors),"errors":errors,"results":results}


@app.post("/api/reset")
def reset(db: Session = Depends(get_db)):
    for model in [QueryTrace, MemoryDecision, MemorySource, ForgetBoundary, EntityAlias, Memory, Entity, Interaction]:
        db.execute(delete(model))
    db.commit()
    return {"ok": True}


@app.get("/api/entities")
def entities(db: Session = Depends(get_db)):
    from app.services.entities import alias_active
    rows=[]
    for entity in db.scalars(select(Entity)):
        certificates=[{"alias":a.alias,"interaction_id":a.interaction_id,"evidence_text":a.evidence_text,"active":alias_active(db,a)}
                      for a in db.scalars(select(EntityAlias).where(EntityAlias.entity_id==entity.id))]
        rows.append({"id":entity.id,"name":entity.name,"kind":entity.kind,"qualifier":entity.qualifier,
                     "aliases":[a["alias"] for a in certificates if a["active"]],"alias_evidence":certificates})
    return rows


@app.get("/api/interactions/{interaction_id}")
def evidence(interaction_id:int,db:Session=Depends(get_db)):
    row=db.get(Interaction,interaction_id)
    if not row: raise HTTPException(404,"Evidence not found")
    return {"id":row.id,"raw_asr":row.raw_asr,"formatted_text":row.formatted_text,"occurred_at":row.occurred_at,
        "app":row.app_context,"style":row.style_context,"processing_status":row.processing_status,"retrieval_blocked":row.retrieval_blocked}

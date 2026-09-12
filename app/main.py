from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db, init_db
from app.models import Interaction, Memory, MemoryDecision, MemorySource, QueryTrace, utcnow
from app.schemas import InteractionIn, MemoryPatch, QueryIn
from app.services.hey_kivi import answer_query
from app.services.memory_engine import process_interaction

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
        occurred_at=payload.occurred_at or utcnow(),
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
    return answer_query(db, payload.query, payload.session_id)


@app.get("/api/memories")
def memories(db: Session = Depends(get_db)):
    rows = db.scalars(select(Memory).order_by(Memory.updated_at.desc())).all()
    return [{
        "id": m.id,
        "memory_type": m.memory_type,
        "subject": m.subject,
        "predicate": m.predicate,
        "value": m.value,
        "canonical_text": m.canonical_text,
        "scope": m.scope,
        "status": m.status,
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
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(m, field, value)
    db.commit(); db.refresh(m)
    return {"ok": True, "id": m.id}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, db: Session = Depends(get_db)):
    m = db.get(Memory, memory_id)
    if not m:
        raise HTTPException(404, "Memory not found")
    m.status = "deleted"
    m.valid_to = utcnow()
    db.commit()
    return {"ok": True}


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
        "created_at": d.created_at,
    } for d in rows]


@app.get("/api/traces")
def traces(db: Session = Depends(get_db)):
    rows = db.scalars(select(QueryTrace).order_by(QueryTrace.id.desc()).limit(100)).all()
    return [{
        "id": t.id,
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
async def import_corpus(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = (await file.read()).decode("utf-8")
    records = []
    if file.filename and file.filename.endswith(".jsonl"):
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        parsed = json.loads(raw)
        records = parsed if isinstance(parsed, list) else parsed.get("records", [])

    processed = 0
    for r in records:
        interaction = Interaction(
            raw_asr=r["raw_asr"],
            formatted_text=r.get("formatted_output") or r.get("formatted_text") or r["raw_asr"],
            app_context=r.get("app") or "other",
            style_context=r.get("style") or "other",
            session_id=r.get("session_id", "import"),
            occurred_at=datetime.fromisoformat(r["timestamp"]) if r.get("timestamp") else utcnow(),
            metadata_json=json.dumps(r.get("metadata", {})),
            hide_mode=bool(r.get("hide_mode", False)),
        )
        db.add(interaction); db.commit(); db.refresh(interaction)
        result = process_interaction(db, interaction)
        if interaction.hide_mode and not any(a["action"] in {"create", "update", "reinforce"} for a in result["actions"]):
            db.delete(interaction)
            db.commit()
        processed += 1
    return {"processed": processed}


@app.post("/api/reset")
def reset(db: Session = Depends(get_db)):
    for model in [QueryTrace, MemoryDecision, MemorySource, Memory, Interaction]:
        db.execute(delete(model))
    db.commit()
    return {"ok": True}

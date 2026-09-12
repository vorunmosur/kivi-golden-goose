from __future__ import annotations

import json
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import MemorySource, QueryTrace
from app.services.memory_contract import GroundedAnswer
from app.services.provider import provider
from app.services.retrieval import retrieve_history, retrieve_memories


def answer_query(db: Session, query: str, session_id: str) -> dict:
    start = time.perf_counter()
    ranked_memories, retrieval_ms = retrieve_memories(db, query)
    memories = [m for m, _ in ranked_memories]
    memory_source_ids = {s.interaction_id for m in memories for s in m.sources}
    # Do not let source-history fallback resurrect a corrected or explicitly forgotten memory.
    # Any interaction already represented in the semantic lifecycle is excluded, regardless of
    # whether its memory is active, superseded, or deleted.
    semanticized_source_ids = set(db.scalars(select(MemorySource.interaction_id)).all())

    # One-off episodes should not be forced into durable semantic memory merely to make Q&A work.
    # Search original history as secondary evidence so arbitrary grounded questions can still resolve.
    history = retrieve_history(db, query, k=6, exclude_ids=semanticized_source_ids)

    memory_context = [
        {
            "memory_id": m.id,
            "score": round(score, 4),
            "type": m.memory_type,
            "subject": m.subject,
            "predicate": m.predicate,
            "value": m.value,
            "canonical_text": m.canonical_text,
            "scope": m.scope,
            "confidence": m.confidence,
            "source_interaction_ids": [s.interaction_id for s in m.sources],
        }
        for m, score in ranked_memories
    ]
    history_context = [
        {
            "interaction_id": it.id,
            "score": round(score, 4),
            "occurred_at": it.occurred_at.isoformat(),
            "app": it.app_context,
            "style": it.style_context,
            "formatted_text": it.formatted_text,
        }
        for it, score in history
    ]
    source_ids = sorted(memory_source_ids | {it.id for it, _ in history})

    usage = {}
    if not memories and not history:
        response = "I don’t know from your saved history yet."
        reason = "No grounded semantic memory or safe source-history evidence was retrieved."
    elif provider.enabled:
        system = """You are Hey Kivi. Answer only from the supplied active semantic memories and source-history evidence.

GROUNDING RULES
- Never invent a missing fact. If the answer is absent or not reasonably derivable, say you do not know from the user's history.
- Prefer active semantic memory for current durable state.
- Use source-history evidence for one-off episodes or details that were correctly not promoted to durable memory.
- If old source evidence conflicts with a newer active semantic memory, prefer the active memory and do not resurrect stale state.
- If evidence is genuinely ambiguous, state the uncertainty instead of choosing silently.
- When drafting text, apply only relevant stored preferences.
- Do not expose credentials/secrets even if source history happens to contain them.
- Return JSON with: answer (string), supported (boolean), used_memory_ids (integer array), used_interaction_ids (integer array).
- Cite only supplied IDs and mark supported=false if the evidence does not answer the question.
- Be concise and useful."""
        result, usage = provider.chat_json(system, json.dumps({
            "query": query,
            "active_semantic_memories": memory_context,
            "source_history_evidence": history_context,
        }, ensure_ascii=False), GroundedAnswer.model_json_schema(), "grounded_answer")
        try:
            result = GroundedAnswer.model_validate(result).model_dump(mode="json")
        except Exception:
            result = {}
        allowed_memory_ids = {m["memory_id"] for m in memory_context}
        allowed_interaction_ids = {h["interaction_id"] for h in history_context} | memory_source_ids
        used_memory_ids = set(result.get("used_memory_ids", [])) if isinstance(result, dict) else set()
        used_interaction_ids = set(result.get("used_interaction_ids", [])) if isinstance(result, dict) else set()
        valid_citations = used_memory_ids <= allowed_memory_ids and used_interaction_ids <= allowed_interaction_ids
        supported = bool(result.get("supported")) if isinstance(result, dict) else False
        answer = str(result.get("answer", "")).strip() if isinstance(result, dict) else ""
        if supported and valid_citations and answer and (used_memory_ids or used_interaction_ids):
            response = answer
            memories = [m for m in memories if m.id in used_memory_ids]
            memory_context = [m for m in memory_context if m["memory_id"] in used_memory_ids]
            history_context = [h for h in history_context if h["interaction_id"] in used_interaction_ids]
            source_ids = sorted(used_interaction_ids | {s.interaction_id for m in memories for s in m.sources})
            reason = "Grounded generation with validated evidence citations."
        else:
            response = "I don’t know from your saved history yet."
            memories = []
            memory_context = []
            history_context = []
            source_ids = []
            reason = "The model did not return a supported answer with valid evidence citations."
    else:
        if memories:
            lines = "; ".join(m.canonical_text for m in memories[:8])
            response = f"From your saved context: {lines}"
            reason = "Offline demo: deterministic summary of retrieved active memories."
        elif history:
            lines = "; ".join(it.formatted_text for it, _ in history[:3])
            response = f"From your history: {lines}"
            reason = "Offline demo: source-history fallback; no semantic memory matched."

    e2e_ms = (time.perf_counter() - start) * 1000
    trace = QueryTrace(
        session_id=session_id,
        query=query,
        response=response,
        retrieved_memory_ids_json=json.dumps([m.id for m in memories]),
        source_interaction_ids_json=json.dumps(source_ids),
        decision_reason=reason,
        retrieval_latency_ms=retrieval_ms,
        end_to_end_latency_ms=e2e_ms,
        model_usage_json=json.dumps(usage),
    )
    db.add(trace); db.commit(); db.refresh(trace)

    return {
        "response": response,
        "memories": memory_context,
        "history_evidence": history_context,
        "trace_id": trace.id,
        "retrieval_latency_ms": round(retrieval_ms, 2),
        "end_to_end_latency_ms": round(e2e_ms, 2),
        "model_usage": usage,
        "reason": reason,
    }

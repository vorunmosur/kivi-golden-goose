from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.db import SessionLocal, init_db
from app.models import Interaction, Memory, MemoryDecision, MemorySource, QueryTrace, utcnow
from app.services.hey_kivi import answer_query
from app.services.memory_engine import process_interaction
from app.services.provider import provider

CORPUS = ROOT / "data" / "dev_corpus.jsonl"
OUT = ROOT / "eval" / "results.json"


def reset(db):
    for model in [QueryTrace, MemoryDecision, MemorySource, Memory, Interaction]:
        db.execute(delete(model))
    db.commit()


def main():
    init_db()
    db = SessionLocal()
    reset(db)
    records = [json.loads(x) for x in CORPUS.read_text(encoding="utf-8").splitlines() if x.strip()]

    t0 = time.perf_counter()
    actions = Counter()
    usage_totals = Counter()
    pipeline_errors = []
    case_results = []
    labeled_total = 0
    labeled_pass = 0
    labeled_failures = []
    expected_actions = {
        "save": {"create", "update", "reinforce"},
        "update": {"update"},
        "reject": {"reject"},
        "ignore": {"ignore"},
        "temporary_or_ignore": {"temporary", "ignore", "create", "reinforce"},
        "save_or_clarify": {"create", "update", "reinforce", "clarify"},
        "clarify_or_save_pattern": {"clarify", "create", "reinforce"},
        "clarify_or_ignore": {"clarify", "ignore"},
    }
    for idx, r in enumerate(records):
        it = Interaction(
            raw_asr=r["raw_asr"],
            formatted_text=r["formatted_output"],
            app_context=r.get("app", "other"),
            style_context=r.get("style", "other"),
            session_id=r.get("session_id", "eval"),
            occurred_at=datetime.fromisoformat(r["timestamp"]) if r.get("timestamp") else utcnow(),
            metadata_json=json.dumps(r.get("metadata", {})),
        )
        db.add(it)
        db.commit()
        db.refresh(it)
        try:
            res = process_interaction(db, it)
        except Exception as exc:
            db.rollback()
            res = {"candidates": [], "actions": [{"action": "error", "reason": str(exc)}], "invalid_candidates": [], "model_usage": {}}
            pipeline_errors.append({"record_index": idx, "stage": "ingest", "error": f"{type(exc).__name__}: {exc}"})
        for key, value in res.get("model_usage", {}).items():
            if isinstance(value, (int, float)):
                usage_totals[key] += value
        for a in res["actions"]:
            actions[a["action"]] += 1
        actual = {a["action"] for a in res["actions"]} or {"ignore"}
        expected = r.get("metadata", {}).get("expected")
        if expected in expected_actions:
            labeled_total += 1
            passed = bool(actual & expected_actions[expected])
            labeled_pass += int(passed)
            if not passed:
                labeled_failures.append({"record_index": idx, "expected": expected, "actual": sorted(actual), "text": r["formatted_output"]})
        affected_memories = []
        for memory_id in {a.get("memory_id") for a in res["actions"] if a.get("memory_id")}:
            memory = db.get(Memory, memory_id)
            if memory:
                affected_memories.append({
                    "id": memory.id,
                    "type": memory.memory_type,
                    "subject": memory.subject,
                    "predicate": memory.predicate,
                    "value": memory.value,
                    "canonical_text": memory.canonical_text,
                    "scope": memory.scope,
                    "status": memory.status,
                    "source_interaction_ids": [source.interaction_id for source in memory.sources],
                })
        case_results.append({
            "record_index": idx,
            "interaction_id": it.id,
            "input": r,
            "candidates": res["candidates"],
            "actions": res["actions"],
            "affected_memories": affected_memories,
            "invalid_candidates": res.get("invalid_candidates", []),
            "model_usage": res.get("model_usage", {}),
        })

    ingest_ms = (time.perf_counter() - t0) * 1000

    query_specs = [
        {"query": "Who is my manager?", "predicate": "manager", "value": "Priya"},
        {"query": "What project am I working on?", "predicate": "current_project", "value": "Golden Goose"},
        {"query": "When is the Golden Goose deadline?", "predicate": "deadline", "value": "Saturday"},
        {"query": "How do I prefer updates?", "predicate": "preference", "value": "concise"},
        {
            "query": "Draft a concise update to my manager about my current project and its deadline.",
            "predicates": ["manager", "current_project", "deadline", "preference"],
        },
        {"query": "What is my passport number?", "refuse": True},
    ]
    qa = []
    for spec in query_specs:
        try:
            result = answer_query(db, spec["query"], "eval")
        except Exception as exc:
            db.rollback()
            result = {"response": "Evaluation error", "memories": [], "history_evidence": [], "model_usage": {}, "reason": str(exc)}
            pipeline_errors.append({"query": spec["query"], "stage": "query", "error": f"{type(exc).__name__}: {exc}"})
        for key, value in result.get("model_usage", {}).items():
            if isinstance(value, (int, float)):
                usage_totals[key] += value
        if spec.get("refuse"):
            passed = not result["memories"] and not result["history_evidence"] and "don’t know" in result["response"].lower()
        elif spec.get("predicates"):
            retrieved_predicates = {m["predicate"] for m in result["memories"]}
            passed = set(spec["predicates"]) <= retrieved_predicates
        else:
            evidence = result["memories"]
            evidence_match = any(
                m["predicate"] == spec["predicate"] and spec["value"].lower() in m["value"].lower()
                for m in evidence
            )
            # A retrieval hit alone is not enough: the user-facing answer must actually surface
            # the expected grounded fact. This prevents an evaluation from passing when the
            # relevant memory was retrieved but omitted from the response.
            answer_match = spec["value"].lower() in result["response"].lower()
            passed = evidence_match and answer_match
        qa.append({"query": spec["query"], "expected": spec, "passed": passed, **result})

    memories = db.scalars(select(Memory)).all()
    active = [m for m in memories if m.status == "active"]
    decisions = db.scalars(select(MemoryDecision)).all()

    secret_like_persisted = [
        m.id for m in active
        if any(x in f"{m.canonical_text} {m.value}".lower() for x in ["api key", "otp", "password", "sk-this-should-never"])
    ]
    missing_provenance = [m.id for m in active if not m.sources]
    unknown_style_interactions = [r for r in records if r.get("style") in {None, "", "unknown"}]

    db_path = ROOT / os.getenv("KIVI_DB_PATH", "kivi.db")
    input_tokens = usage_totals.get("prompt_tokens", usage_totals.get("input_tokens", 0))
    output_tokens = usage_totals.get("completion_tokens", usage_totals.get("output_tokens", 0))
    input_rate = float(os.getenv("KIVI_INPUT_COST_PER_1M", "0") or 0)
    output_rate = float(os.getenv("KIVI_OUTPUT_COST_PER_1M", "0") or 0)
    estimated_cost = ((input_tokens * input_rate) + (output_tokens * output_rate)) / 1_000_000 if (input_rate or output_rate) else None
    results = {
        "evaluation_mode": "model" if provider.enabled else "offline_regression",
        "record_count": len(records),
        "ingest_ms": round(ingest_ms, 2),
        "avg_ingest_ms": round(ingest_ms / max(1, len(records)), 3),
        "db_size_bytes": os.path.getsize(db_path) if db_path.exists() else None,
        "memory_count_total": len(memories),
        "memory_count_active": len(active),
        "decision_count": len(decisions),
        "actions": dict(actions),
        "model_usage_total": dict(usage_totals),
        "estimated_cost_usd": round(estimated_cost, 6) if estimated_cost is not None else None,
        "cost_note": "Set KIVI_INPUT_COST_PER_1M and KIVI_OUTPUT_COST_PER_1M for the selected provider/model to calculate cost." if estimated_cost is None else "Calculated from configured per-million-token rates.",
        "pipeline_errors": pipeline_errors,
        "admission_evaluation": {
            "labeled_records": labeled_total,
            "passed": labeled_pass,
            "accuracy": round(labeled_pass / max(1, labeled_total), 4),
            "failures": labeled_failures[:50],
        },
        "guardrail_assertions": {
            "secret_like_persisted_ids": secret_like_persisted,
            "secret_guardrail_pass": len(secret_like_persisted) == 0,
            "active_memories_missing_provenance": missing_provenance,
            "provenance_pass": len(missing_provenance) == 0,
            "unknown_style_record_count": len(unknown_style_interactions),
            "generic_path_exercised": len(unknown_style_interactions) > 0,
        },
        "queries": qa,
        "query_evaluation": {
            "passed": sum(int(q["passed"]) for q in qa),
            "total": len(qa),
        },
        "inspectable_cases": case_results,
        "failures_visible": True,
        "note": "Model-backed evaluation quality requires KIVI_LLM_API_KEY (or the OPENAI_API_KEY compatibility fallback). Offline mode only smoke-tests persistence and deterministic guardrails.",
    }
    OUT.write_text(json.dumps(results, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(results, indent=2, default=str, ensure_ascii=False))
    db.close()


if __name__ == "__main__":
    main()

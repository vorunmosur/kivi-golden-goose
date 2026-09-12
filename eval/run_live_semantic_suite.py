from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Interaction, Memory, MemoryDecision, MemorySource, QueryTrace, utcnow
from app.services.hey_kivi import answer_query
from app.services.memory_engine import process_interaction
from app.services.provider import provider

OUT = ROOT / "eval" / "live_semantic_results.json"


def reset(db):
    for model in [QueryTrace, MemoryDecision, MemorySource, Memory, Interaction]:
        db.execute(delete(model))
    db.commit()


def ingest(db, text: str, *, style: str | None = "other", app: str = "other", when=None):
    row = Interaction(
        raw_asr=text,
        formatted_text=text,
        app_context=app,
        style_context=style or "",
        session_id="live-suite",
        occurred_at=when or utcnow(),
        metadata_json="{}",
        hide_mode=False,
    )
    db.add(row); db.commit(); db.refresh(row)
    return row, process_interaction(db, row)


def active(db):
    return db.scalars(select(Memory).where(Memory.status == "active")).all()


def values_for(db, predicate: str):
    return [m.value for m in active(db) if m.predicate == predicate]


def record(results, name: str, passed: bool, details):
    results.append({"name": name, "passed": bool(passed), "details": details})


def main():
    if not provider.enabled:
        print("SKIP: configure KIVI_LLM_API_KEY (or OPENAI_API_KEY fallback) for the live suite.")
        return 0

    init_db()
    db = SessionLocal()
    reset(db)
    results = []
    t0 = utcnow()

    # 1) Current-state creation + correction.
    _, r1 = ingest(db, "Rajeev is my manager.", style="work messaging", app="Slack", when=t0)
    _, r2 = ingest(db, "Correction: Priya is my manager now.", style="work messaging", app="Slack", when=t0 + timedelta(minutes=1))
    managers = [m for m in db.scalars(select(Memory).where(Memory.predicate == "manager")).all()]
    record(results, "manager_correction", any(m.status == "active" and "priya" in m.value.lower() for m in managers) and any(m.status == "superseded" and "rajeev" in m.value.lower() for m in managers), {"first": r1, "second": r2, "memories": [(m.value, m.status, m.scope) for m in managers]})

    # 2) Semantically scoped communication preference.
    _, r = ingest(db, "For emails to my manager, I prefer concise bullet-point updates.", style="email", app="Gmail")
    prefs = [m for m in active(db) if m.memory_type == "preference"]
    record(results, "scoped_email_preference", any(m.scope == "work:email" and ("concise" in m.value.lower() or "bullet" in m.value.lower()) for m in prefs), {"result": r, "preferences": [(m.value, m.scope) for m in prefs]})

    # 3) Source context must not incorrectly partition a global fact.
    _, r = ingest(db, "My home city is Bengaluru.", style="developer", app="VS Code")
    homes = [m for m in active(db) if "bengaluru" in m.value.lower()]
    record(results, "global_fact_from_developer_context", any(m.scope == "global" for m in homes), {"result": r, "matches": [(m.predicate, m.value, m.scope) for m in homes]})

    # 4) Weak behavioral inference should not silently become a durable fact.
    before_ids = {m.id for m in active(db)}
    _, r = ingest(db, "I usually keep things pretty short, I guess.", style="other", app="other")
    new_active = [m for m in active(db) if m.id not in before_ids]
    actions = {a.get("action") for a in r.get("actions", [])}
    record(results, "weak_inference_not_silently_promoted", not new_active or bool(actions & {"clarify", "ignore"}), {"result": r, "new_active": [(m.predicate, m.value) for m in new_active]})

    # 5) Credential guardrail.
    _, r = ingest(db, "Use this API key: sk-abcdefghijklmnop123456.", style="developer", app="VS Code")
    leaked = [m for m in active(db) if "sk-abcdefghijklmnop123456" in (m.value + " " + m.canonical_text)]
    record(results, "credential_rejection", not leaked and any(a.get("action") == "reject" for a in r.get("actions", [])), {"result": r})

    # 6) Temporary/episodic information should not look permanently timeless.
    _, r = ingest(db, "Meet Arjun at 3 PM tomorrow.", style="work messaging", app="Slack")
    episodes = [m for m in active(db) if m.memory_type == "episode" or "arjun" in m.value.lower()]
    record(results, "temporary_episode", any(m.expires_at is not None or m.memory_type == "episode" for m in episodes) or any(a.get("action") in {"temporary", "ignore"} for a in r.get("actions", [])), {"result": r, "matches": [(m.memory_type, m.value, str(m.expires_at)) for m in episodes]})

    # 7) Explicit forgetting.
    _, pref_create = ingest(db, "I prefer dark mode for coding.", style="developer", app="VS Code")
    _, pref_delete = ingest(db, "Forget that I prefer dark mode for coding.", style="developer", app="VS Code")
    dark_active = [m for m in active(db) if "dark mode" in (m.value + " " + m.canonical_text).lower()]
    record(results, "explicit_forget", not dark_active and any(a.get("action") == "delete" for a in pref_delete.get("actions", [])), {"create": pref_create, "delete": pref_delete})

    # 8) Unsupported question must refuse rather than invent.
    unsupported = answer_query(db, "What is my brother's favorite restaurant?", "live-suite")
    refusal = "don’t know" in unsupported["response"].lower() or "don't know" in unsupported["response"].lower()
    record(results, "unsupported_refusal", refusal, unsupported)

    # 9) Distributed evidence synthesis.
    ingest(db, "I am working on Golden Goose.", style="developer", app="VS Code")
    ingest(db, "The deadline for Golden Goose is Saturday.", style="work messaging", app="Slack")
    distributed = answer_query(db, "Draft a concise update to my manager about my current project and its deadline.", "live-suite")
    lower = distributed["response"].lower()
    record(results, "distributed_evidence", all(x in lower for x in ["priya", "golden goose", "saturday"]), distributed)

    # 10) Missing/unknown Style must still use the generic path.
    _, r = ingest(db, "Remember that my timezone is IST.", style=None, app="unknown")
    timezone_matches = [m for m in active(db) if "ist" in m.value.lower() or "timezone" in m.predicate.lower()]
    record(results, "unknown_style_generic_path", bool(timezone_matches), {"result": r, "matches": [(m.predicate, m.value, m.scope) for m in timezone_matches]})

    summary = {
        "mode": "live_model_semantic_suite",
        "provider_base_url": settings.base_url,
        "llm_model": settings.llm_model,
        "embedding_model": settings.embedding_model,
        "passed": sum(int(x["passed"]) for x in results),
        "total": len(results),
        "results": results,
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str, ensure_ascii=False))
    db.close()
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Interaction, Memory, MemorySource, QueryTrace
from app.services import memory_engine
from app.services import hey_kivi
from app.services.hey_kivi import answer_query
from app.services.retrieval import retrieve_history, retrieve_memories


def db_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return Session(engine, autoflush=False)


def interaction(db: Session, text: str, when: datetime, style: str = "unknown", hide: bool = False) -> Interaction:
    row = Interaction(
        raw_asr=text.lower(), formatted_text=text, app_context="unknown",
        style_context=style, session_id="test", occurred_at=when,
        metadata_json="{}", hide_mode=hide,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def candidate(value: str, predicate: str = "manager", cardinality: str = "single", change: str = "assert") -> dict:
    return {
        "memory_type": "relationship", "subject": "user", "predicate": predicate,
        "value": value, "canonical_text": f"{predicate}: {value}", "scope": "global",
        "confidence": 0.96, "explicitness": "explicit", "temporal": "durable",
        "sensitivity": "normal", "proposed_action": "create_or_update",
        "cardinality": cardinality, "change_kind": change, "reason": "explicit statement",
        "supersedes_predicate": None, "expiry_days": None,
    }


def run_with(db: Session, monkeypatch, row: Interaction, value: dict):
    monkeypatch.setattr(memory_engine, "extract_candidates", lambda _db, _row: ([value], {}, []))
    value["evidence_text"]=row.formatted_text
    return memory_engine.process_interaction(db, row)


def test_correction_supersedes_and_preserves_provenance(monkeypatch):
    db = db_session()
    t0 = datetime(2026, 9, 1, 9)
    first = interaction(db, "Rajeev is my manager.", t0)
    run_with(db, monkeypatch, first, candidate("Rajeev"))
    second = interaction(db, "My manager changed to Priya.", t0 + timedelta(days=1))
    result = run_with(db, monkeypatch, second, candidate("Priya", change="correct"))

    rows = db.scalars(select(Memory).order_by(Memory.id)).all()
    assert [m.status for m in rows] == ["superseded", "active"]
    assert rows[0].valid_to == second.occurred_at
    assert rows[1].value == "Priya"
    assert [s.interaction_id for s in rows[1].sources] == [second.id]
    assert result["actions"][0]["action"] == "update"


def test_out_of_order_evidence_cannot_replace_current_state(monkeypatch):
    db = db_session()
    newest = interaction(db, "Priya is my manager.", datetime(2026, 9, 5))
    run_with(db, monkeypatch, newest, candidate("Priya"))
    older = interaction(db, "Rajeev is my manager.", datetime(2026, 9, 1))
    result = run_with(db, monkeypatch, older, candidate("Rajeev"))

    active = db.scalars(select(Memory).where(Memory.status == "active")).all()
    assert [m.value for m in active] == ["Priya"]
    assert db.scalars(select(Memory).where(Memory.status=="historical")).one().value=="Rajeev"


def test_multi_value_knowledge_coexists(monkeypatch):
    db = db_session()
    t0 = datetime(2026, 9, 1)
    for i, name in enumerate(("Aaditya", "Maya")):
        row = interaction(db, f"{name} reviews my work.", t0 + timedelta(hours=i))
        run_with(db, monkeypatch, row, candidate(name, "reviewer", "multi", "add"))
    active = db.scalars(select(Memory).where(Memory.status == "active")).all()
    assert {m.value for m in active} == {"Aaditya", "Maya"}


def test_inferred_candidate_is_never_silently_admitted(monkeypatch):
    db = db_session()
    row = interaction(db, "I often send updates early.", datetime(2026, 9, 1))
    c = candidate("send updates early", "behavior_pattern", "multi")
    c["explicitness"] = "inferred"
    result = run_with(db, monkeypatch, row, c)
    assert result["actions"][0]["action"] == "clarify"
    assert db.scalars(select(Memory)).all() == []


def test_forget_request_deletes_only_the_semantic_match(monkeypatch):
    db = db_session()
    t0 = datetime(2026, 9, 1)
    for i, value in enumerate(("concise emails", "bullet-point updates")):
        row = interaction(db, f"I prefer {value}.", t0 + timedelta(hours=i))
        run_with(db, monkeypatch, row, candidate(value, "preference", "multi"))

    forget = interaction(db, "Forget that I prefer concise emails.", t0 + timedelta(days=1))
    delete_candidate = candidate("prefer concise emails", "preference", "multi", "remove")
    delete_candidate["proposed_action"] = "delete"
    result = run_with(db, monkeypatch, forget, delete_candidate)

    assert result["actions"][0]["action"] == "delete"
    rows = db.scalars(select(Memory).order_by(Memory.id)).all()
    assert [(m.value, m.status) for m in rows] == [
        ("concise emails", "deleted"), ("bullet-point updates", "active")
    ]


def test_hidden_and_secret_history_are_not_retrievable():
    db = db_session()
    hidden = interaction(db, "Project Falcon is confidential.", datetime(2026, 9, 1), hide=True)
    secret = interaction(db, "My API key is sk-abcdefghijklmnop.", datetime(2026, 9, 2))
    assert retrieve_history(db, "Falcon") == []
    assert retrieve_history(db, "API key") == []


def test_deleted_memory_source_cannot_resurface_through_history():
    db = db_session()
    row = interaction(db, "My favorite editor is Helix.", datetime(2026, 9, 1))
    memory = Memory(
        memory_type="preference", subject="user", predicate="editor", value="Helix",
        canonical_text="The user prefers Helix.", scope="work:developer", status="deleted",
        confidence=0.9, sensitivity="normal", source_style="developer",
        explicitness="explicit", valid_from=row.occurred_at, valid_to=datetime(2026, 9, 2),
    )
    db.add(memory)
    db.flush()
    db.add(MemorySource(memory_id=memory.id, interaction_id=row.id, evidence_text=row.formatted_text))
    db.commit()

    result = answer_query(db, "What editor do I prefer?", "test")
    assert result["response"].startswith("I don’t know")
    assert result["memories"] == []
    assert result["history_evidence"] == []


def test_compound_query_retrieves_distributed_evidence():
    db = db_session()
    facts = [
        ("user", "manager", "Priya", "Priya is the user's manager."),
        ("user", "current_project", "Golden Goose", "The user's current project is Golden Goose."),
        ("Golden Goose", "deadline", "Saturday", "Golden Goose is due Saturday."),
        ("user", "preference", "concise updates", "The user prefers concise updates."),
    ]
    for subject, predicate, value, canonical in facts:
        db.add(Memory(
            memory_type="fact", subject=subject, predicate=predicate, value=value,
            canonical_text=canonical, scope="global", status="active", confidence=0.95,
            sensitivity="normal", source_style="unknown", explicitness="explicit",
        ))
    db.commit()
    ranked, _ = retrieve_memories(
        db, "Draft a concise update to my manager about my current project and its deadline."
    )
    assert {m.predicate for m, _ in ranked} >= {"manager", "current_project", "deadline", "preference"}


def test_model_answer_requires_valid_evidence_citations(monkeypatch):
    db = db_session()
    row = interaction(db, "Priya is my manager.", datetime(2026, 9, 1))
    memory = Memory(
        memory_type="relationship", subject="user", predicate="manager", value="Priya",
        canonical_text="Priya is the user's manager.", scope="global", status="active",
        confidence=0.98, sensitivity="normal", source_style="unknown",
        explicitness="explicit", valid_from=row.occurred_at,
    )
    db.add(memory)
    db.flush()
    db.add(MemorySource(memory_id=memory.id, interaction_id=row.id, evidence_text=row.formatted_text))
    db.commit()
    db.refresh(memory)

    monkeypatch.setattr(hey_kivi, "retrieve_memories", lambda *_args, **_kwargs: ([(memory, 0.9)], 1.0))
    monkeypatch.setattr(hey_kivi, "retrieve_history", lambda *_args, **_kwargs: [])
    from app.services.query_context import QueryPlan
    monkeypatch.setattr(hey_kivi, "plan_query", lambda *_args, **_kwargs: (QueryPlan(predicates=["manager"]),set(),{}))
    monkeypatch.setattr(hey_kivi.provider, "enabled", True)
    monkeypatch.setattr(hey_kivi.provider, "chat_json", lambda *_args, **_kwargs: ({
        "answer": "Priya is your manager.", "supported": True,
        "claims": [{"text":"Priya is your manager.","evidence":["E9999"]}], "applied_preferences": [],
    }, {}))

    result = answer_query(db, "Who is my manager?", "test")
    assert result["response"].startswith("I don’t know")
    assert result["memories"] == []


def test_model_answer_preserves_only_cited_provenance(monkeypatch):
    db = db_session()
    row = interaction(db, "Priya is my manager.", datetime(2026, 9, 1))
    memory = Memory(
        memory_type="relationship", subject="user", predicate="manager", value="Priya",
        canonical_text="Priya is the user's manager.", scope="global", status="active",
        confidence=0.98, sensitivity="normal", source_style="unknown",
        explicitness="explicit", valid_from=row.occurred_at,
    )
    db.add(memory)
    db.flush()
    db.add(MemorySource(memory_id=memory.id, interaction_id=row.id, evidence_text=row.formatted_text))
    db.commit()
    db.refresh(memory)

    monkeypatch.setattr(hey_kivi, "retrieve_memories", lambda *_args, **_kwargs: ([(memory, 0.9)], 1.0))
    monkeypatch.setattr(hey_kivi, "retrieve_history", lambda *_args, **_kwargs: [])
    from app.services.query_context import QueryPlan
    monkeypatch.setattr(hey_kivi, "plan_query", lambda *_args, **_kwargs: (QueryPlan(predicates=["manager"]),set(),{}))
    monkeypatch.setattr(hey_kivi.provider, "enabled", True)
    def fake_chat(*args,**kwargs):
        if args[-1]=="evidence_verdict": return {"supported":True,"reason":"Claim matches evidence."},{}
        return {"answer":"Priya is your manager.","supported":True,"applied_preferences":[],
            "claims":[{"text":"Priya is your manager.","evidence":["E1"]}]},{"prompt_tokens":10,"completion_tokens":5}
    monkeypatch.setattr(hey_kivi.provider,"chat_json",fake_chat)

    result = answer_query(db, "Who is my manager?", "test")
    assert result["response"] == "Priya is your manager."
    assert [m["memory_id"] for m in result["memories"]] == [memory.id]
    trace = db.get(QueryTrace, result["trace_id"])
    assert json.loads(trace.source_interaction_ids_json) == [row.id]

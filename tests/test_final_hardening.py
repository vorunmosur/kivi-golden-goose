from datetime import datetime

from app.models import Interaction
from app.models import Memory
from app.services.answer_evidence import necessary_evidence
from app.services.answer_realization import proposition
from app.services.lifecycle import canonicalize_relationship_candidate
from app.services.memory_engine import transient_chatter_candidate
from app.services.query_context import QueryPlan
from tests.test_answer_evidence import record


def test_single_valued_role_relationship_is_canonicalized():
    candidate = {
        "memory_type": "relationship",
        "subject": "Aaditya",
        "predicate": "reviewer",
        "value": "Golden Goose",
        "cardinality": "single",
        "canonical_text": "Aaditya reviews Golden Goose.",
        "evidence_text": "Aaditya reviews Golden Goose.",
        "subject_qualifier": "",
        "value_qualifier": "",
        "entities": [
            {"name": "Aaditya", "kind": "person"},
            {"name": "Golden Goose", "kind": "project"},
        ],
    }

    result = canonicalize_relationship_candidate(candidate)

    assert result["subject"] == "Golden Goose"
    assert result["predicate"] == "reviewer"
    assert result["value"] == "Aaditya"


def test_multi_valued_relationship_is_not_reversed():
    candidate = {
        "memory_type": "relationship",
        "subject": "Aaditya",
        "predicate": "reviewer",
        "value": "Golden Goose",
        "cardinality": "multi",
        "canonical_text": "Aaditya reviews Golden Goose.",
        "evidence_text": "Aaditya reviews Golden Goose.",
        "entities": [
            {"name": "Aaditya", "kind": "person"},
            {"name": "Golden Goose", "kind": "project"},
        ],
    }

    result = canonicalize_relationship_candidate(candidate)

    assert result["subject"] == "Aaditya"
    assert result["value"] == "Golden Goose"


def test_requested_semantic_predicates_survive_draft_evidence_filter():
    """Planner-requested uses/date slots survive even without literal 'technology' wording."""
    from app.services.answer_evidence import necessary_evidence
    from app.services.query_context import QueryPlan

    plan = QueryPlan(
        intent="draft",
        predicates=["deadline", "uses"],
        project="alpha",
    )

    memories = [
        {
            "type": "fact",
            "predicate": "deadline",
            "subject": "Alpha",
            "value": "Friday",
            "canonical_text": "The deadline for Alpha is Friday.",
        },
        {
            "type": "fact",
            "predicate": "uses",
            "subject": "Alpha",
            "value": "FastAPI",
            "canonical_text": "Alpha uses FastAPI.",
        },
    ]

    chosen, _ = necessary_evidence(
        "Draft an update saying Alpha is due Friday and uses FastAPI.",
        plan,
        memories,
        [],
    )

    assert {m["predicate"] for m in chosen} == {"deadline", "uses"}


def test_structured_draft_keeps_multiple_requested_supported_facts():
    """A grounded draft must not silently drop one of two supplied requested facts."""
    from app.services.answer_realization import realize_draft

    mapping = {
        "E1": {
            "kind": "memory",
            "record": {
                "type": "fact",
                "subject": "Alpha",
                "subject_qualifier": "",
                "predicate": "uses",
                "value": "FastAPI",
                "value_qualifier": "",
                "status": "active",
                "temporal_status": "current",
                "certainty": "confirmed",
                "scope": '{"project":"alpha"}',
                "source_evidence": [],
            },
        },
        "E2": {
            "kind": "memory",
            "record": {
                "type": "fact",
                "subject": "Alpha",
                "subject_qualifier": "",
                "predicate": "deadline",
                "value": "Friday",
                "value_qualifier": "",
                "status": "active",
                "temporal_status": "current",
                "certainty": "confirmed",
                "scope": '{"project":"alpha"}',
                "source_evidence": [],
            },
        },
    }

    result, _ = realize_draft(
        "Draft a concise update saying Alpha is due Friday and uses FastAPI.",
        mapping,
    )

    assert "FastAPI" in result["answer"]
    assert "Friday" in result["answer"]
    assert len(result["claims"]) == 2


def test_boolean_uses_true_realizes_predicate_object():
    row = record(
        "fact",
        subject="Willow Clinic",
        predicate="uses_calendar_slots",
        value="true",
    )

    result = proposition("E1", row)

    assert result is not None
    assert result.sentence == "Willow Clinic uses calendar slots."
    assert "uses true" not in result.sentence.casefold()


def test_boolean_uses_false_realizes_negation():
    row = record(
        "fact",
        subject="Willow Clinic",
        predicate="uses_calendar_slots",
        value="false",
    )

    result = proposition("E1", row)

    assert result is not None
    assert result.sentence == "Willow Clinic does not use calendar slots."


def test_nonboolean_uses_value_preserves_value():
    row = record(
        "fact",
        subject="Coral Survey",
        predicate="uses_equipment",
        value="sonar",
    )

    result = proposition("E1", row)

    assert result is not None
    assert result.sentence == "Coral Survey uses sonar."


def test_forget_instruction_excluded_from_unrelated_draft():
    memories = [
        record(
            "fact",
            subject="Cedar Archive",
            predicate="deadline",
            value="January 10, 2027",
            memory_id=1,
        ),
        record(
            "fact",
            subject="Cedar Archive",
            predicate="memory_instruction",
            value="keep the old date forgotten",
            memory_id=2,
        ),
    ]

    selected, _ = necessary_evidence(
        "Draft a Cedar Archive deadline update.",
        QueryPlan(intent="draft"),
        memories,
        [],
    )

    assert any(m["predicate"] == "deadline" for m in selected)
    assert not any(m["predicate"] == "memory_instruction" for m in selected)


def test_memory_management_request_can_retain_memory_instruction():
    memories = [
        record(
            "fact",
            subject="Cedar Archive",
            predicate="memory_instruction",
            value="keep the old date forgotten",
            memory_id=1,
        ),
    ]

    selected, _ = necessary_evidence(
        "Draft a note about what I asked you to keep forgotten in memory.",
        QueryPlan(intent="draft"),
        memories,
        [],
    )

    assert any(m["predicate"] == "memory_instruction" for m in selected)


def _interaction(text: str) -> Interaction:
    return Interaction(
        raw_asr=text.casefold(),
        formatted_text=text,
        app_context="unknown",
        style_context="unknown",
        session_id="hardening-test",
        occurred_at=datetime(2026, 9, 20, 12, 0),
        metadata_json="{}",
        hide_mode=False,
    )


def _candidate(
    *,
    memory_type="fact",
    subject="user",
    predicate="status",
    value="test",
    explicitness="inferred",
):
    return {
        "memory_type": memory_type,
        "subject": subject,
        "predicate": predicate,
        "value": value,
        "canonical_text": f"{subject} {predicate} {value}",
        "explicitness": explicitness,
        "proposed_action": "create_or_update",
    }


def test_pure_microphone_test_is_transient():
    row = _interaction("Testing microphone.")

    assert transient_chatter_candidate(
        _candidate(predicate="microphone_test"),
        row,
    )


def test_acknowledgement_is_transient():
    row = _interaction("Cool, thanks.")

    assert transient_chatter_candidate(
        _candidate(predicate="acknowledgement"),
        row,
    )


def test_real_microphone_episode_is_not_transient():
    row = _interaction(
        "My microphone stopped working during yesterday's customer interview."
    )

    candidate = _candidate(
        memory_type="episode",
        predicate="microphone_failure",
        value="microphone stopped working during customer interview",
    )

    assert not transient_chatter_candidate(candidate, row)


def test_explicit_microphone_preference_is_not_transient():
    row = _interaction("I prefer the Shure MV7 microphone.")

    candidate = _candidate(
        memory_type="preference",
        predicate="preferred_microphone",
        value="Shure MV7",
        explicitness="explicit",
    )

    assert not transient_chatter_candidate(candidate, row)

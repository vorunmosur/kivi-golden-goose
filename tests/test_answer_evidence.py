from datetime import datetime, timedelta
import copy
import json
import pytest
from app.services.answer_evidence import evidence_handles, map_answer, deterministic_support, temporal_support, necessary_evidence
from app.services.query_context import QueryPlan

NOW = datetime(2026, 9, 18, 12)


def record(kind="episode", date="2026-09-18T10:00:00", **kw):
    return {"memory_id": 617, "type": kind, "subject": "user", "predicate": "resolved" if kind == "episode" else "uses", "value": "scanner glare" if kind == "episode" else "TIFF", "canonical_text": "Recorded assertion", "scope": "global", "status": "active", "certainty": "confirmed", "temporal_status": "current", "valid_from": date, "valid_until": None, "source_evidence": [{"interaction_id": 902, "excerpt": "I resolved scanner glare.", "occurred_at": date}], **kw}


def answer(text, handles=None):
    return {"answer": text, "supported": True, "claims": [{"text": text, "evidence": handles or ["E1"]}], "applied_preferences": []}


def test_handles_map_exact_provenance_without_database_id_generation():
    public, mapping = evidence_handles([record()], [])
    assert "memory_id" not in json.dumps(
        public) and "interaction_id" not in json.dumps(public)
    mapped = map_answer(answer("I resolved scanner glare."), mapping)
    assert mapped["used_memory_ids"] == [
        617] and mapped["used_interaction_ids"] == [902]
    assert mapped["claims"][0]["interaction_ids"] == [902]


@pytest.mark.parametrize("handle", ["E0", "E2", "902", "e1"])
def test_out_of_pack_handles_rejected(handle):
    _, mapping = evidence_handles([record()], [])
    with pytest.raises(ValueError):
        map_answer(answer("A claim", [handle]), mapping)


def test_preferences_cannot_smuggle_nonpreference_reference():
    _, mapping = evidence_handles([record()], [])
    raw = answer("A claim")
    raw["applied_preferences"] = ["E1"]
    with pytest.raises(ValueError):
        map_answer(raw, mapping)


@pytest.mark.parametrize("term,age", [("today", 0), ("yesterday", 1), ("this week", 2), ("earlier this week", 2), ("currently", 0), ("recently", 5), ("just completed", 0), ("still", 0)])
def test_supported_and_stale_relative_events(term, age):
    date = (NOW-timedelta(days=age, hours=1)).isoformat()
    text = "I "+("just completed the scan" if term ==
                 "just completed" else "resolved the scan "+term)
    current = {"kind": "memory", "record": record(date=date)}
    assert not temporal_support(text, [current], NOW)
    stale = {"kind": "memory", "record": record(date="2026-07-01T10:00:00")}
    assert temporal_support(text, [stale], NOW)


@pytest.mark.parametrize("term", ["currently", "still", "today"])
def test_durable_current_state_can_have_old_source(term):
    assert not temporal_support("We "+term+" use TIFF.", [
                                {"kind": "memory", "record": record("fact", date="2026-07-01T10:00:00")}], NOW)


def test_recent_reinforcement_does_not_redate_old_episode():
    r = record(date="2026-07-01T10:00:00")
    r["source_evidence"][0]["occurred_at"] = NOW.isoformat()
    assert temporal_support("I resolved it today.", [
                            {"kind": "memory", "record": r}], NOW)


def test_unclaimed_temporal_phrase_cannot_bypass_guard():
    _, mapping = evidence_handles([record()], [])
    raw = answer("I resolved it.")
    raw["answer"] = "I resolved it yesterday."
    assert deterministic_support(raw, mapping, NOW)


def test_active_ongoing_episode_supports_currently_even_with_old_source():
    r = record(
        "episode",
        date="2026-09-01T10:00:00",
        predicate="contributing_to",
        value="Falcon rollout",
        canonical_text="I'm contributing to the Falcon rollout.",
    )
    wrapped = {"kind": "memory", "record": r}

    assert not temporal_support(
        "I am currently contributing to the Falcon rollout.",
        [wrapped],
        NOW,
    )


def test_old_point_in_time_episode_does_not_support_currently():
    r = record(
        "episode",
        date="2026-09-01T10:00:00",
        predicate="met",
        value="Aaditya",
        canonical_text="I met Aaditya.",
    )
    r["temporal_status"] = "historical"
    r["status"] = "historical"

    wrapped = {"kind": "memory", "record": r}

    assert temporal_support(
        "I am currently meeting Aaditya.",
        [wrapped],
        NOW,
    )


def test_minimal_tools_and_date_draft_omits_incidental_episodes():
    mem = [record(), record("fact"), record("fact", predicate="deadline", value="October 10"),
           record("preference", predicate="email_style", value="concise")]
    chosen, history = necessary_evidence("Write an update with equipment and delivery date", QueryPlan(
        intent="draft"), mem, [{"formatted_text": "An old incident"}])
    assert [m["type"] for m in chosen] == [
        "fact", "fact", "preference"] and history == []


def test_explicit_incident_request_preserves_episode():
    chosen, _ = necessary_evidence(
        "Draft what happened during the incident", QueryPlan(intent="draft"), [record()], [])
    assert chosen


def test_same_name_people_need_distinct_qualified_rendering():
    records = [record("relationship", subject="Alex", subject_entity_id=i,
                      subject_qualifier=q) for i, q in [(12, "museum"), (29, "cycling club")]]
    _, mapping = evidence_handles(records, [])
    assert deterministic_support(
        answer("Alex from museum and cycling club helped.", ["E1", "E2"]), mapping, NOW)
    assert not deterministic_support(answer(
        "Alex from museum and Alex from cycling club helped.", ["E1", "E2"]), mapping, NOW)


@pytest.mark.parametrize("text", ["See the attached list.", "We will monitor the project.", "We are continuing to monitor it."])
def test_invented_deliverables_and_commitments_fail(text):
    _, mapping = evidence_handles([record()], [])
    assert deterministic_support(answer(text), mapping, NOW)


def test_dated_direct_quote_preserves_source_relative_words():
    r = record(date="2026-07-08T10:00:00")
    r["source_evidence"][0]["excerpt"] = "Today I resolved scanner glare."
    claim = 'On July 8, 2026, I said "Today I resolved scanner glare."'
    assert not temporal_support(claim, [{"kind": "memory", "record": r}], NOW)


def test_literal_ambiguous_alias_cannot_be_resolved_by_planner_guess(monkeypatch):
    from tests.test_memory_lifecycle import db_session
    from tests.test_v2_behavior import learn
    from app.services.query_context import plan_query
    from app.services import query_context
    db = db_session()
    for person, project in [("Katherine Vale", "Silver Atlas"), ("Katrina Moss", "Copper Vale")]:
        text = f"{person} is also called Kat. {person} reviews {project}."
        learn(db, monkeypatch, text, project, subject=person, predicate="reviews", entities=[
              {"name": person, "kind": "person", "qualifier": "", "aliases": ["Kat"], "evidence_text": text}])
    monkeypatch.setattr(query_context.provider, "enabled", True)
    monkeypatch.setattr(query_context.provider, "chat_json", lambda *a: (
        {"intent": "current", "entities": ["Katrina Moss"], "predicates": ["reviews"]}, {}))
    plan, ids, _ = plan_query(db, "What does Kat review?")
    assert plan.clarification and "Which kat" in plan.clarification


def test_hallucinated_ambiguous_planner_entity_cannot_force_clarification(monkeypatch):
    from tests.test_memory_lifecycle import db_session
    from tests.test_v2_behavior import learn
    from app.services.query_context import plan_query
    from app.services import query_context
    db = db_session()
    for person, project in [("Felix Reed", "Maple Workshop"), ("Felix Stone", "Coral Survey")]:
        text = f"{person} reviews {project}."
        learn(db, monkeypatch, text, project, subject=person, predicate="reviews", entities=[
              {"name": person, "kind": "person", "qualifier": project, "aliases": ["Felix"], "evidence_text": text}])
    monkeypatch.setattr(query_context.provider, "enabled", True)
    monkeypatch.setattr(query_context.provider, "chat_json", lambda *a: (
        {"intent": "draft", "entities": ["Juniper Festival", "Felix"], "predicates": ["purpose"]}, {}))
    plan, _, _ = plan_query(db, "Write a detailed client email summarizing Juniper Festival.", context={
                            "project": "Juniper Festival"})
    assert not plan.clarification and "Felix" not in plan.entities


@pytest.mark.parametrize("term", ["yesterday", "this week", "earlier this week"])
def test_confirmed_past_state_supported_by_validity_interval(term):
    r = record("relationship", date="2026-09-14T00:00:00",
               valid_until="2026-09-18T00:00:00", status="superseded", temporal_status="historical")
    assert not temporal_support(
        "Mira was my coordinator "+term, [{"kind": "memory", "record": r}], NOW)
    r["valid_until"] = "2026-09-01T00:00:00"
    r["valid_from"] = "2026-08-01T00:00:00"
    assert temporal_support("Mira was my coordinator " +
                            term, [{"kind": "memory", "record": r}], NOW)


def test_answer_currently_can_match_plain_confirmed_state_claim():
    _, mapping = evidence_handles([record("relationship", subject="Cedar Archive",
                                  predicate="coordinator", value="Mira", date="2026-07-01T10:00:00")], [])
    raw = answer("Mira is the coordinator of Cedar Archive.")
    raw["answer"] = "Mira currently coordinates Cedar Archive."
    assert not deterministic_support(raw, mapping, NOW)


def test_dated_source_quote_need_not_repeat_relative_word_in_claim():
    r = record(date="2026-07-08T10:00:00")
    r["source_evidence"][0]["excerpt"] = "Today I resolved scanner glare."
    _, mapping = evidence_handles([r], [])
    raw = answer("I resolved scanner glare on July 8, 2026.")
    raw["answer"] = "On July 8, 2026, I said: 'Today I resolved scanner glare.'"
    assert not deterministic_support(raw, mapping, NOW)


def test_unclaimed_current_processing_not_supported_by_file_format():
    _, mapping = evidence_handles([record(
        "fact", subject="Cedar Archive", predicate="format", value="TIFF", date="2026-07-01T10:00:00")], [])
    raw = answer("Cedar Archive uses TIFF.")
    raw["answer"] = "We are currently processing materials and converting everything into TIFF."
    assert deterministic_support(raw, mapping, NOW)


def test_draft_renderer_excludes_uncited_attachment_but_keeps_cited_facts():
    from app.services.answer_evidence import render_draft
    raw = answer("Cedar Archive uses TIFF.")
    raw["answer"] = "Cedar Archive uses TIFF. See the attached list."
    rendered = render_draft(raw)
    assert rendered["answer"] == "Cedar Archive uses TIFF."
    assert raw["answer"].endswith("attached list.")


def test_draft_renderer_does_not_repair_bad_claim_references():
    from app.services.answer_evidence import render_draft
    _, mapping = evidence_handles([record()], [])
    with pytest.raises(ValueError):
        map_answer(render_draft(
            answer("An unsupported fact", ["E999"])), mapping)


@pytest.mark.parametrize("slot", ["uses_material", "uses_irrigation_method"])
def test_minimal_draft_preserves_descriptive_uses_slots(slot):
    chosen, _ = necessary_evidence("Write about our tool and delivery date", QueryPlan(
        intent="draft"), [record("fact", predicate=slot, value="independent equipment")], [])
    assert len(chosen) == 1

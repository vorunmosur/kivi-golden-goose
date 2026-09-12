from app.services.context_policy import policy_for
from app.services.memory_engine import _looks_sensitive, _normalize_scope


def test_developer_rejects_api_key_language():
    p = policy_for("developer")
    assert _looks_sensitive("my api key is sk-abc1234567890123", p.never_store_patterns)


def test_unknown_style_falls_back_to_generic_policy():
    assert policy_for("completely unknown style").name == "other"
    assert policy_for(None).name == "other"


def test_context_is_not_hard_partition_for_global_relationship():
    candidate = {
        "predicate": "manager",
        "canonical_text": "Priya is the user's manager.",
        "value": "Priya",
        "scope": "auto",
    }
    assert _normalize_scope(candidate, policy_for("developer").default_scope) == "global"


def test_semantically_scoped_preference_beats_source_context():
    candidate = {
        "predicate": "communication_preference",
        "canonical_text": "User prefers concise emails.",
        "value": "concise emails",
        "scope": "auto",
    }
    assert _normalize_scope(candidate, policy_for("personal messaging").default_scope) == "work:email"

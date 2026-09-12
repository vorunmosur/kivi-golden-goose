from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    fact = "fact"
    preference = "preference"
    relationship = "relationship"
    project = "project"
    episode = "episode"


class Explicitness(str, Enum):
    explicit = "explicit"
    implied = "implied"
    inferred = "inferred"


class TemporalKind(str, Enum):
    durable = "durable"
    temporary = "temporary"
    unknown = "unknown"


class Sensitivity(str, Enum):
    normal = "normal"
    sensitive = "sensitive"
    secret = "secret"


class ProposedAction(str, Enum):
    create_or_update = "create_or_update"
    delete = "delete"
    clarify = "clarify"
    ignore = "ignore"
    reject = "reject"


class Cardinality(str, Enum):
    single = "single"   # one current value per subject/predicate/scope, e.g. current manager
    multi = "multi"     # multiple co-existing values are legitimate, e.g. collaborators


class ChangeKind(str, Enum):
    assert_value = "assert"
    replace = "replace"
    correct = "correct"
    add = "add"
    remove = "remove"


class MemoryCandidate(BaseModel):
    """LLM proposal, never a direct database write command.

    Natural-language interpretation remains model-driven, while deterministic code owns durable
    invariants: secret rejection, hide-mode boundaries, deletion, confidence thresholds, and
    single-vs-multi valued reconciliation.
    """

    model_config = ConfigDict(extra="forbid")

    memory_type: MemoryType
    subject: str = Field(default="user", min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=200, description="Stable semantic key when one is meaningful")
    value: str = Field(min_length=1, max_length=4000)
    canonical_text: str = Field(min_length=1, max_length=4000)
    scope: str = Field(default="global", min_length=1, max_length=160)
    confidence: float = Field(ge=0.0, le=1.0)
    explicitness: Explicitness
    temporal: TemporalKind = TemporalKind.unknown
    sensitivity: Sensitivity = Sensitivity.normal
    proposed_action: ProposedAction
    cardinality: Cardinality = Cardinality.multi
    change_kind: ChangeKind = ChangeKind.assert_value
    reason: str = Field(min_length=1, max_length=1000)
    supersedes_predicate: str | None = Field(default=None, max_length=200)
    expiry_days: int | None = Field(default=None, ge=1, le=3650)


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[MemoryCandidate] = Field(default_factory=list, max_length=12)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    supported: bool
    used_memory_ids: list[int] = Field(default_factory=list)
    used_interaction_ids: list[int] = Field(default_factory=list)

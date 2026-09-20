from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class MemoryType(str, Enum):
    fact = "fact"
    preference = "preference"
    relationship = "relationship"
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


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: str | None = None
    context: str | None = None
    project: str | None = None
    recipient: str | None = None


class EntityMention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: Literal["person", "project", "organization", "tool", "other"] = "other"
    qualifier: str = ""
    aliases: list[str] = Field(default_factory=list)
    evidence_text: str


class MemoryCandidate(BaseModel):
    """LLM proposal, never a direct database write command.

    Natural-language interpretation remains model-driven, while deterministic code owns durable
    invariants: secret rejection, hide-mode boundaries, deletion, confidence thresholds, and
    single-vs-multi valued reconciliation.
    """

    model_config = ConfigDict(extra="forbid")

    memory_type: MemoryType
    subject: str = Field(min_length=1,max_length=200,description="Entity this assertion describes; never default ownership to user.")
    predicate: str = Field(min_length=1, max_length=200, description="Stable semantic key when one is meaningful")
    value: str = Field(min_length=1, max_length=4000)
    canonical_text: str = Field(min_length=1, max_length=4000)
    scope: Scope | str = "global"
    evidence_text: str = ""
    certainty: Literal["confirmed", "tentative"] = "confirmed"
    temporal_status: Literal["current", "future", "historical"] = "current"
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    subject_qualifier: str = ""
    value_qualifier: str = ""
    entities: list[EntityMention] = Field(default_factory=list)
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


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    memory_ids: list[int] = Field(default_factory=list)
    interaction_ids: list[int] = Field(default_factory=list)


class GroundedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    supported: bool
    claims: list[Claim] = Field(default_factory=list)
    used_memory_ids: list[int] = Field(default_factory=list)
    used_interaction_ids: list[int] = Field(default_factory=list)


class EvidenceVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supported: bool
    reason: str


class ForgetVerdict(BaseModel):
    model_config=ConfigDict(extra="forbid")
    supported: bool
    reason: str
    alias_ids: list[int]=Field(default_factory=list)

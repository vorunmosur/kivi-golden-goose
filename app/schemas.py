from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InteractionIn(BaseModel):
    raw_asr: str
    formatted_text: str
    app_context: str = "other"
    style_context: str = "other"
    session_id: str = "default"
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    hide_mode: bool = False


class QueryIn(BaseModel):
    query: str
    session_id: str = "hey-kivi"


class MemoryPatch(BaseModel):
    value: str | None = None
    canonical_text: str | None = None
    scope: str | None = None
    status: str | None = None


class CorpusRecord(BaseModel):
    raw_asr: str
    formatted_output: str
    timestamp: datetime | None = None
    app: str = "other"
    style: str = "other"
    session_id: str = "import"
    metadata: dict[str, Any] = Field(default_factory=dict)

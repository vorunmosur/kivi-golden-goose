from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_asr: Mapped[str] = mapped_column(Text)
    formatted_text: Mapped[str] = mapped_column(Text)
    app_context: Mapped[str] = mapped_column(String(80), default="other")
    style_context: Mapped[str] = mapped_column(String(80), default="other")
    session_id: Mapped[str] = mapped_column(String(120), default="default")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    hide_mode: Mapped[bool] = mapped_column(Boolean, default=False)

    sources: Mapped[list[MemorySource]] = relationship(back_populates="interaction", cascade="all, delete-orphan")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_type: Mapped[str] = mapped_column(String(40))  # fact / preference / episode / relationship / project
    subject: Mapped[str] = mapped_column(String(200), default="user")
    predicate: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    canonical_text: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(160), default="global")
    status: Mapped[str] = mapped_column(String(30), default="active")  # active/superseded/deleted/pending
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    sensitivity: Mapped[str] = mapped_column(String(30), default="normal")
    source_style: Mapped[str] = mapped_column(String(80), default="other")
    explicitness: Mapped[str] = mapped_column(String(30), default="implicit")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    sources: Mapped[list[MemorySource]] = relationship(back_populates="memory", cascade="all, delete-orphan")


class MemorySource(Base):
    __tablename__ = "memory_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id", ondelete="CASCADE"))
    interaction_id: Mapped[int] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"))
    evidence_text: Mapped[str] = mapped_column(Text)

    memory: Mapped[Memory] = relationship(back_populates="sources")
    interaction: Mapped[Interaction] = relationship(back_populates="sources")


class MemoryDecision(Base):
    __tablename__ = "memory_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interaction_id: Mapped[int] = mapped_column(ForeignKey("interactions.id", ondelete="CASCADE"))
    candidate_json: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(30))  # create/update/ignore/clarify/temporary/reject
    reason: Mapped[str] = mapped_column(Text)
    memory_id: Mapped[int | None] = mapped_column(ForeignKey("memories.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class QueryTrace(Base):
    __tablename__ = "query_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(120), default="hey-kivi")
    query: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    retrieved_memory_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_interaction_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    decision_reason: Mapped[str] = mapped_column(Text)
    retrieval_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    end_to_end_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    model_usage_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

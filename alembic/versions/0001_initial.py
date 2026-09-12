"""initial semantic memory schema

Revision ID: 0001_initial
Revises: 
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("interactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_asr", sa.Text(), nullable=False),
        sa.Column("formatted_text", sa.Text(), nullable=False),
        sa.Column("app_context", sa.String(80), nullable=False),
        sa.Column("style_context", sa.String(80), nullable=False),
        sa.Column("session_id", sa.String(120), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("hide_mode", sa.Boolean(), nullable=False),
    )
    op.create_table("memories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_type", sa.String(40), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("predicate", sa.String(200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(160), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("sensitivity", sa.String(30), nullable=False),
        sa.Column("source_style", sa.String(80), nullable=False),
        sa.Column("explicitness", sa.String(30), nullable=False),
        sa.Column("valid_from", sa.DateTime(), nullable=True),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
    )
    op.create_table("memory_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("memory_id", sa.Integer(), sa.ForeignKey("memories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interaction_id", sa.Integer(), sa.ForeignKey("interactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
    )
    op.create_table("memory_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interaction_id", sa.Integer(), sa.ForeignKey("interactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_json", sa.Text(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("memory_id", sa.Integer(), sa.ForeignKey("memories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table("query_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(120), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("retrieved_memory_ids_json", sa.Text(), nullable=False),
        sa.Column("source_interaction_ids_json", sa.Text(), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("retrieval_latency_ms", sa.Float(), nullable=False),
        sa.Column("end_to_end_latency_ms", sa.Float(), nullable=False),
        sa.Column("model_usage_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("query_traces")
    op.drop_table("memory_decisions")
    op.drop_table("memory_sources")
    op.drop_table("memories")
    op.drop_table("interactions")

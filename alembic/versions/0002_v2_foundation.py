"""Evidence backed V2 lifecycle and entity foundation."""
from alembic import op
import sqlalchemy as sa
from app.db import Base
from app import models
revision="0002_v2_foundation"
down_revision="0001_initial"
branch_labels=None
depends_on=None


def upgrade():
    bind=op.get_bind()
    for name in ["entities", "entity_aliases", "forget_boundaries"]:
        Base.metadata.tables[name].create(bind, checkfirst=True)
    additions={
        "interactions": [("embedding_json",sa.Text(),None),("embedding_model",sa.String(160),None),("retrieval_blocked",sa.Boolean(),"0"),("processing_status",sa.String(30),"complete")],
        "memories": [("certainty",sa.String(30),"confirmed"),("temporal_status",sa.String(30),"current"),("subject_entity_id",sa.Integer(),None),("value_entity_id",sa.Integer(),None),("embedding_model",sa.String(160),None)],
        "memory_decisions": [("previous_state_json",sa.Text(),"[]"),("new_state_json",sa.Text(),"[]"),("decision_maker",sa.String(160),"v1")],
        "query_traces": [("context_json",sa.Text(),"{}")],
    }
    for table, columns in additions.items():
        with op.batch_alter_table(table) as batch:
            for name,kind,default in columns:
                batch.add_column(sa.Column(name,kind,nullable=default is None,server_default=default))
    with op.batch_alter_table("memories") as batch:
        batch.create_foreign_key("fk_memory_subject_entity","entities",["subject_entity_id"],["id"])
        batch.create_foreign_key("fk_memory_value_entity","entities",["value_entity_id"],["id"])
        batch.create_index("ix_memories_subject_entity_id",["subject_entity_id"])
        batch.create_index("ix_memories_value_entity_id",["value_entity_id"])
    # Backfill normalized entity identity and conservative legacy lifecycle.
    rows=bind.execute(sa.text("SELECT id,subject,memory_type,status FROM memories")).mappings().all()
    entities={}
    for row in rows:
        key=" ".join(row["subject"].casefold().split())
        if key not in entities:
            existing=bind.execute(sa.text("SELECT id FROM entities WHERE normalized_name=:name AND qualifier=''"),{"name":key}).scalar()
            if not existing:
                existing=bind.execute(sa.text("INSERT INTO entities(name,normalized_name,kind,qualifier) VALUES(:name,:norm,'other','')"),{"name":row["subject"],"norm":key}).lastrowid
            entities[key]=existing
        bind.execute(sa.text("UPDATE memories SET subject_entity_id=:entity WHERE id=:id"),{"entity":entities[key],"id":row["id"]})
    bind.execute(sa.text("UPDATE memories SET memory_type='fact' WHERE memory_type='project'"))
    bind.execute(sa.text("UPDATE memories SET temporal_status='historical' WHERE status='superseded'"))
    # Legacy deleted slots receive boundaries; raw duplicates must not resurrect them.
    bind.execute(sa.text("INSERT INTO forget_boundaries(subject,predicate,scope,value,occurred_at) SELECT lower(subject),lower(predicate),scope,lower(value),coalesce(valid_to,updated_at) FROM memories WHERE status='deleted'"))


def downgrade():
    raise RuntimeError("V2 contains lifecycle evidence; restore a backup to downgrade safely.")

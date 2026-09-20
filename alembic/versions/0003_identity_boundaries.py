"""Keep forget boundaries scoped to resolved entity identities."""
from alembic import op
import sqlalchemy as sa

revision="0003_identity_boundaries"
down_revision="0002_v2_foundation"
branch_labels=None
depends_on=None


def upgrade():
    # 0002 creates auxiliary tables from metadata; fresh installs already have these fields.
    columns={c["name"] for c in sa.inspect(op.get_bind()).get_columns("forget_boundaries")}
    missing=[field for field in ("subject_entity_id","value_entity_id") if field not in columns]
    if missing:
        with op.batch_alter_table("forget_boundaries") as batch:
            for field in missing:
                batch.add_column(sa.Column(field,sa.Integer(),nullable=True))
                batch.create_foreign_key("fk_boundary_"+field.removesuffix("_id"),"entities",[field],["id"])
                batch.create_index("ix_forget_boundaries_"+field,[field])
    # Legacy null identity boundaries deliberately retain conservative text matching.


def downgrade():
    raise RuntimeError("Forget boundaries are privacy evidence; restore a backup to downgrade safely.")

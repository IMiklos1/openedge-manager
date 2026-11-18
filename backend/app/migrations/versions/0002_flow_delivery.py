"""Persist immutable artifacts and the state of a targeted C2 flow update."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.create_table(
        "flow_artifacts",
        sa.Column("flow_id", sa.String(64), sa.ForeignKey("flows.id"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("runtime_version", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    with op.batch_alter_table("deployments") as batch:
        batch.add_column(sa.Column("agent_id", sa.String(128)))
        batch.add_column(sa.Column("ack_state", sa.String(32)))
        batch.add_column(sa.Column("acknowledged_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("applied_at", sa.DateTime(timezone=True)))
        batch.create_foreign_key("fk_deployments_agent_id", "agents", ["agent_id"], ["id"])
    active = sa.text("agent_id IS NOT NULL AND status IN ('PENDING', 'DISPATCHED', 'ACKNOWLEDGED')")
    op.create_index("uq_deployments_active_agent", "deployments", ["agent_id"], unique=True,
                    postgresql_where=active, sqlite_where=active)

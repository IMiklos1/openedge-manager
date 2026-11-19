"""Keep each saved flow revision and index deployment history."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    versions = op.create_table(
        "flow_revisions",
        sa.Column("flow_id", sa.String(64), sa.ForeignKey("flows.id"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    flows = sa.table(
        "flows", sa.column("id"), sa.column("current_version"), sa.column("name"),
        sa.column("description"), sa.column("definition"), sa.column("created_at"),
    )
    op.execute(versions.insert().from_select(
        ["flow_id", "version", "name", "description", "definition", "created_at"],
        sa.select(flows.c.id, flows.c.current_version, flows.c.name, flows.c.description,
                  flows.c.definition, flows.c.created_at),
    ))
    op.create_index("ix_deployments_history", "deployments", ["created_at", "id"])
    op.create_index("ix_deployments_flow_history", "deployments", ["flow_id", "created_at", "id"])
    op.create_index("ix_deployments_agent_history", "deployments", ["agent_id", "created_at", "id"])

"""Adopt or create the schema shipped before versioned migrations."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "agents",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("hostname", sa.String(255)),
        sa.Column("os_name", sa.String(100)),
        sa.Column("architecture", sa.String(50)),
        sa.Column("runtime", sa.String(100)),
        sa.Column("runtime_version", sa.String(100)),
        sa.Column("agent_class", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("reported_flow_version", sa.Integer(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "flows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("flow_id", sa.String(64), sa.ForeignKey("flows.id"), nullable=False),
        sa.Column("flow_version", sa.Integer(), nullable=False),
        sa.Column("target_class", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        if_not_exists=True,
    )
    op.create_table(
        "c2_probes",
        sa.Column("agent_id", sa.String(128), sa.ForeignKey("agents.id"), primary_key=True),
        sa.Column("operation_id", sa.String(36), nullable=False, unique=True),
        sa.Column("ack_state", sa.String(32)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        if_not_exists=True,
    )

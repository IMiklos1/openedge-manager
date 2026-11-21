"""Record the runtime of published artifacts, including existing Java artifacts."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.add_column("flow_artifacts", sa.Column("runtime", sa.String(100), nullable=False, server_default="minifi-java"))

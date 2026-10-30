"""Durable SSE admission shared by all API processes."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "stream_leases",
        sa.Column("lease_id", sa.String(36), primary_key=True),
        sa.Column(
            "principal_id", sa.String(), sa.ForeignKey("principals.principal_id"), nullable=False
        ),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=False),
        sa.Column("lease_until", sa.Float(), nullable=False),
    )
    op.create_index("ix_stream_leases_principal_id", "stream_leases", ["principal_id"])


def downgrade():
    op.drop_table("stream_leases")

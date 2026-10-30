"""Durable worker presence, with no inferred legacy observations."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "worker_presence",
        sa.Column(
            "principal_id", sa.String(), sa.ForeignKey("principals.principal_id"), primary_key=True
        ),
        sa.Column("executor", sa.String(), nullable=False),
        sa.Column("observed_at", sa.Float(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("worker_presence")

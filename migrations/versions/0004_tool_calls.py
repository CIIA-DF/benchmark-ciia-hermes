"""Histórico de tentativas de tool por execução, sem argumentos em claro."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tool_calls",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column("tool_call_id", sa.String(), primary_key=True),
        sa.Column("attempt", sa.Integer(), primary_key=True),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("replayed", sa.Boolean(), nullable=False),
        sa.Column("artifact_id", sa.String(), nullable=True),
        sa.Column("args_sha256", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("tool_calls")

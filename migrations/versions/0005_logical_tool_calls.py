"""Durable binding of logical tool IDs, preserving original attempt history."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "logical_tool_calls",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column("tool_call_id", sa.String(), primary_key=True),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("args_sha256", sa.String(), nullable=False),
    )
    # First observed input owns the historical ID. Inconsistent later attempts stay
    # in the audit trail, but cannot redefine the identity after migration.
    attempts = sa.table(
        "tool_calls",
        sa.column("run_id"),
        sa.column("tool_call_id"),
        sa.column("attempt"),
        sa.column("tool"),
        sa.column("args_sha256"),
    )
    first = sa.select(
        attempts.c.run_id, attempts.c.tool_call_id, attempts.c.tool, attempts.c.args_sha256
    ).where(attempts.c.attempt == 1)
    op.get_bind().execute(
        table.insert().from_select(["run_id", "tool_call_id", "tool", "args_sha256"], first)
    )


def downgrade():
    op.drop_table("logical_tool_calls")

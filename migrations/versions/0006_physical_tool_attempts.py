"""Physical attempts and phases; legacy records are never backfilled or reinterpreted."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "physical_tool_attempts",
        sa.Column("attempt_id", sa.String(36), primary_key=True),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), nullable=True),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column("args_sha256", sa.String(), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("response_state", sa.String(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(), nullable=True),
        sa.Column("client_received", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_physical_tool_attempts_run_id", "physical_tool_attempts", ["run_id"])
    op.create_table(
        "physical_tool_phases",
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("physical_tool_attempts.attempt_id"),
            primary_key=True,
        ),
        sa.Column("phase", sa.String(), primary_key=True),
        sa.Column("recorded_at", sa.Float(), nullable=False),
        sa.Column(
            "artifact_id", sa.String(), sa.ForeignKey("artifacts.artifact_id"), nullable=True
        ),
        sa.Column("replayed", sa.Boolean(), nullable=True),
    )


def downgrade():
    op.drop_table("physical_tool_phases")
    op.drop_index("ix_physical_tool_attempts_run_id", table_name="physical_tool_attempts")
    op.drop_table("physical_tool_attempts")

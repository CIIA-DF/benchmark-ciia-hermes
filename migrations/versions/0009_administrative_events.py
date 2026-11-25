"""Administrative changes without credential material or inferred legacy events."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "administrative_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "principal_id", sa.String(), sa.ForeignKey("principals.principal_id"), nullable=False
        ),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.Float(), nullable=False),
        sa.Column("credential_changed", sa.Boolean(), nullable=False),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=False),
    )


def downgrade():
    op.drop_table("administrative_events")

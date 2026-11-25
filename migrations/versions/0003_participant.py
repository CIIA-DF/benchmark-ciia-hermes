"""Marcador pseudônimo de análise, independente das permissões técnicas."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversations", sa.Column("participant_id", sa.String(36), nullable=True))
    op.create_index("ix_conversations_participant_id", "conversations", ["participant_id"])


def downgrade():
    op.drop_index("ix_conversations_participant_id", table_name="conversations")
    op.drop_column("conversations", "participant_id")

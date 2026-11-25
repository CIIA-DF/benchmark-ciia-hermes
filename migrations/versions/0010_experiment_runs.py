"""Registro experimental com revisões, portado do task/langgraph-grafo (856ff06, João Enomoto).

Mesmas tabelas da migração SQL original (experiment_runs e experiment_run_revisions), agora
ligadas a runs e com instante de gravação. Não infere registros para runs anteriores.
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "experiment_runs",
        sa.Column("run_id", sa.String(), sa.ForeignKey("runs.run_id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "experiment_run_revisions",
        sa.Column("run_id", sa.String(), sa.ForeignKey("experiment_runs.run_id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.Float(), nullable=False),
    )


def downgrade():
    # Remove os registros experimentais; aplicar somente após backup e aprovação.
    op.drop_table("experiment_run_revisions")
    op.drop_table("experiment_runs")

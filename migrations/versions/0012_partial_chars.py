"""Contador de caracteres parciais por run (P9a, item 9 da auditoria de 30/10).

Cada ``text_delta`` relia todos os deltas anteriores para conferir o limite de 100.000
caracteres, um custo que crescia com o run. ``runs.partial_chars`` guarda o total, atualizado sob
a mesma trava do run que já protege ``event_sequence``. O preenchimento soma os deltas já
gravados; não infere nada que não esteja em ``run_events``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "runs", sa.Column("partial_chars", sa.Integer(), nullable=False, server_default="0")
    )
    connection = op.get_bind()
    events = sa.table(
        "run_events",
        sa.column("run_id", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("payload", sa.JSON()),
    )
    runs = sa.table("runs", sa.column("run_id", sa.String()), sa.column("partial_chars"))
    totals: dict[str, int] = {}
    rows = connection.execute(
        sa.select(events.c.run_id, events.c.payload).where(events.c.kind == "text_delta")
    )
    for run_id, payload in rows:
        text = payload.get("text", "") if isinstance(payload, dict) else ""
        totals[run_id] = totals.get(run_id, 0) + len(text)
    for run_id, total in totals.items():
        connection.execute(
            sa.update(runs).where(runs.c.run_id == run_id).values(partial_chars=total)
        )


def downgrade():
    op.drop_column("runs", "partial_chars")

"""Recusa atualizar bancos que ainda guardam U+0000 em texto (P3).

Desde o P3 os contratos recusam U+0000, e linhas antigas com esse caractere passariam a falhar
na leitura (por exemplo, 500 depois da reserva no claim). Esta revisão não altera dados: só
procura o caractere em todas as colunas de texto e JSON e interrompe a atualização, sem expor
conteúdo, quando o encontra. Tratamento: docs/04-operacoes/validacao-p.md.
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

NUL = "\x00"


def _contains_nul(value) -> bool:
    if isinstance(value, str):
        return NUL in value
    if isinstance(value, dict):
        return any(_contains_nul(k) or _contains_nul(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_nul(item) for item in value)
    return False


def _cell_has_nul(raw, is_json: bool) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return _contains_nul(raw)
    if NUL in raw:
        return True
    if is_json and "\\u0000" in raw:
        # Só confirma depois de decodificar, para não acusar uma barra invertida literal.
        try:
            return _contains_nul(json.loads(raw))
        except ValueError:
            return False
    return False


def legacy_nul_columns(connection) -> list[tuple[str, str, int]]:
    """(tabela, coluna, linhas) com U+0000; não lê nem devolve o conteúdo encontrado."""
    metadata = sa.MetaData()
    metadata.reflect(bind=connection)
    found = []
    for table in sorted(metadata.tables.values(), key=lambda item: item.name):
        if table.name == "alembic_version":
            continue
        for column in table.columns:
            is_json = isinstance(column.type, sa.JSON)
            if not (is_json or isinstance(column.type, sa.String)):
                continue
            rows = connection.execute(
                sa.select(sa.cast(column, sa.Text)).where(column.is_not(None))
            )
            count = sum(1 for (raw,) in rows if _cell_has_nul(raw, is_json))
            if count:
                found.append((table.name, column.name, count))
    return found


def upgrade():
    found = legacy_nul_columns(op.get_bind())
    if found:
        where = ", ".join(f"{table}.{column} ({count})" for table, column, count in found)
        raise RuntimeError(
            "Banco com U+0000 em texto, recusado pelos contratos desde o P3: "
            f"{where}. Faça backup e trate as linhas antes de atualizar "
            "(docs/04-operacoes/validacao-p.md)."
        )


def downgrade():
    pass

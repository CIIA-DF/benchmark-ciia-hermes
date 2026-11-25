"""P3: banco antigo com U+0000 não é atualizado em silêncio (migração 0011)."""

import pytest
from sqlalchemy import insert

from services.backend.migrate import migrate, schema_revisions
from services.backend.schema import requirements
from services.backend.storage import make_engine, processes


@pytest.fixture
def legacy(tmp_path):
    database = make_engine(f"sqlite:///{tmp_path / 'legacy-nul.db'}")
    migrate(database, "0010")
    yield database
    database.dispose()


def revision(database):
    with database.connect() as conn:
        return schema_revisions(conn)[0]


@pytest.mark.parametrize(
    ("table", "row", "where"),
    [
        (
            processes,
            {"process_id": "PROC-NUL", "corpus_version": "v1", "payload": {"title": "a\x00b"}},
            "processes.payload (1)",
        ),
        (
            requirements,
            {
                "process_id": "PROC-NUL",
                "corpus_version": "v1",
                "requirements_version": "r1",
                "requirement_id": "REQ\x00",
                "payload": {"description": "ok"},
            },
            "requirements.requirement_id (1)",
        ),
    ],
)
def test_upgrade_stops_on_legacy_nul_without_changing_data(legacy, table, row, where):
    with legacy.begin() as conn:
        conn.execute(insert(table).values(**row))
    with pytest.raises(RuntimeError, match=r"U\+0000") as error:
        migrate(legacy)
    assert where in str(error.value)
    # Nada é exposto nem alterado: o banco continua na 0010 com a linha original.
    assert "a\x00b" not in str(error.value) and "REQ\x00" not in str(error.value)
    assert revision(legacy) == "0010"
    with legacy.connect() as conn:
        assert conn.execute(table.select()).one()


def test_upgrade_passes_without_nul_and_ignores_escaped_backslash(legacy):
    with legacy.begin() as conn:
        conn.execute(
            insert(processes).values(
                process_id="PROC-OK", corpus_version="v1", payload={"title": r"literal \u0000"}
            )
        )
    migrate(legacy)
    assert revision(legacy) == "0011"

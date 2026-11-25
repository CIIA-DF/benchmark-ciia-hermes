import pytest
from sqlalchemy import JSON, Column, MetaData, String, Table, inspect, select

from pipelines.documents.ingest import chunk_document
from scripts.checklist import import_checklist
from services.backend.migrate import migrate
from services.backend.schema import requirements
from services.backend.storage import chunks, documents, ingest, initialize, make_engine, processes


def test_legacy_migration_preserves_corpus_and_rejects_schema_drift(tmp_path, corpus):
    database = make_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    baseline = MetaData()
    for table in (processes, documents, chunks):
        table.to_metadata(baseline)
    baseline.create_all(database)
    process, document = corpus
    ingest(database, process, document, chunk_document(document))
    initialize(database)
    with database.connect() as conn:
        assert conn.execute(select(processes.c.payload)).scalar_one()["process_id"] == (
            process.process_id
        )
    assert "runs" in inspect(database).get_table_names()
    migrate(database, "0001", downgrade=True)
    assert "runs" not in inspect(database).get_table_names()
    initialize(database)
    database.dispose()

    drift = make_engine(f"sqlite:///{tmp_path / 'drift.db'}")
    metadata = MetaData()
    Table("unknown", metadata, Column("id", String, primary_key=True))
    metadata.create_all(drift)
    with pytest.raises(RuntimeError, match="incompatível"):
        initialize(drift)
    assert inspect(drift).get_table_names() == ["unknown"]
    drift.dispose()


def test_checklist_is_immutable_and_transactional(engine, corpus):
    process, document = corpus
    ingest(engine, process, document, chunk_document(document))
    values = [{"requirement_id": "REQ-1", "description": "Descrição fictícia", "source": "Teste"}]
    args = (engine, process.process_id, process.corpus_version, process.requirements_version)
    import_checklist(*args, values)
    import_checklist(*args, values)
    with pytest.raises(ValueError, match="imutável"):
        import_checklist(*args, [{**values[0], "description": "Alterada"}])
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(requirements.c.payload).where(
                    requirements.c.process_id == process.process_id
                )
            )
            .scalars()
            .all()
        )
        assert rows == values


def test_legacy_with_incompatible_primary_key_is_not_stamped(tmp_path):
    database = make_engine(f"sqlite:///{tmp_path / 'bad-primary-key.db'}")
    broken = MetaData()
    Table(
        "processes",
        broken,
        Column("process_id", String, primary_key=True),
        Column("corpus_version", String, nullable=False),
        Column("payload", JSON, nullable=False),
    )
    for table in (documents, chunks):
        table.to_metadata(broken)
    broken.create_all(database)
    try:
        with pytest.raises(RuntimeError, match="incompatível"):
            initialize(database)
        assert "alembic_version" not in inspect(database).get_table_names()
    finally:
        database.dispose()

"""Atualização revisada de schema; adoção do legado apenas após comparação exata."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, inspect, text


def migrate(engine, revision="head", *, downgrade=False):
    from services.backend.storage import chunks, documents, processes

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(20261020)"))
        config.attributes["connection"] = connection
        names = set(inspect(connection).get_table_names())
        legacy = {"processes", "documents", "chunks"}
        if "alembic_version" not in names and names:
            expected = MetaData()
            for table in (processes, documents, chunks):
                table.to_metadata(expected)
            differences = compare_metadata(MigrationContext.configure(connection), expected)
            incompatible_keys = names == legacy and any(
                inspect(connection).get_pk_constraint(table.name)["constrained_columns"]
                != [column.name for column in table.primary_key.columns]
                for table in expected.tables.values()
            )
            if names != legacy or differences or incompatible_keys:
                raise RuntimeError("Schema legado incompatível: faça backup e revise a migração.")
            command.stamp(config, "0001")
        if downgrade:
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)

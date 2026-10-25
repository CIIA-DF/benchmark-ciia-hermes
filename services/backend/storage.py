"""Persistência transacional mínima; dados de cada corpus são imutáveis."""

import os
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    ForeignKeyConstraint,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from contracts.models import Chunk, Document, Process

metadata = MetaData()
processes = Table(
    "processes",
    metadata,
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
    Column("payload", JSON, nullable=False),
)
documents = Table(
    "documents",
    metadata,
    Column("process_id", String, primary_key=True),
    Column("corpus_version", String, primary_key=True),
    Column("document_id", String, primary_key=True),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(
        ["process_id", "corpus_version"], ["processes.process_id", "processes.corpus_version"]
    ),
)
chunks = Table(
    "chunks",
    metadata,
    Column("chunk_id", String, primary_key=True),
    Column("process_id", String, nullable=False, index=True),
    Column("corpus_version", String, nullable=False),
    Column("document_id", String, nullable=False),
    Column("text", String, nullable=False),
    Column("payload", JSON, nullable=False),
    ForeignKeyConstraint(
        ["process_id", "corpus_version", "document_id"],
        ["documents.process_id", "documents.corpus_version", "documents.document_id"],
    ),
)


def make_engine(url: str | None = None) -> Engine:
    url = url or os.getenv("DATABASE_URL", "sqlite:///./data/demo.db")
    if url == "sqlite:///./data/demo.db":
        Path("data").mkdir(exist_ok=True)
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def initialize(engine: Engine) -> None:
    from services.backend.migrate import migrate

    migrate(engine)


def ingest(engine: Engine, process: Process, document: Document, items: list[Chunk]) -> int:
    if (document.process_id, document.corpus_version) != (
        process.process_id,
        process.corpus_version,
    ):
        raise ValueError("Documento não pertence ao processo/corpus informado.")
    pages = {page.number: page.text for page in document.pages}
    for item in items:
        if (
            (item.process_id, item.document_id, item.corpus_version, item.source)
            != (process.process_id, document.document_id, process.corpus_version, document.source)
            or item.page not in pages
            or pages[item.page][item.start : item.end] != item.text
        ):
            raise ValueError("Chunk sem rastreabilidade válida.")
    if not items or len({item.chunk_id for item in items}) != len(items):
        raise ValueError("Informe chunks não vazios e com IDs únicos.")
    with engine.begin() as connection:
        for table, key, payload in [
            (
                processes,
                {"process_id": process.process_id, "corpus_version": process.corpus_version},
                process,
            ),
            (
                documents,
                {
                    "process_id": document.process_id,
                    "corpus_version": document.corpus_version,
                    "document_id": document.document_id,
                },
                document,
            ),
        ]:
            existing = connection.execute(
                select(table.c.payload).filter_by(**key)
            ).scalar_one_or_none()
            serialized = payload.model_dump(mode="json")
            if existing is not None and existing != serialized:
                raise ValueError("Corpus imutável: alteração exige nova corpus_version.")
            if existing is None:
                connection.execute(insert(table).values(**key, payload=serialized))
        existing_items = (
            connection.execute(
                select(chunks.c.payload).where(
                    chunks.c.process_id == process.process_id,
                    chunks.c.corpus_version == process.corpus_version,
                    chunks.c.document_id == document.document_id,
                )
            )
            .scalars()
            .all()
        )
        expected = {item.chunk_id: item.model_dump(mode="json") for item in items}
        if existing_items:
            if {item["chunk_id"]: item for item in existing_items} != expected:
                raise ValueError("Chunking diferente: gere nova corpus_version.")
            return 0
        connection.execute(
            insert(chunks),
            [
                dict(
                    chunk_id=item.chunk_id,
                    process_id=item.process_id,
                    corpus_version=item.corpus_version,
                    document_id=item.document_id,
                    text=item.text,
                    payload=item.model_dump(mode="json"),
                )
                for item in items
            ],
        )
    return len(items)

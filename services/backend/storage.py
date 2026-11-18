"""Persistência transacional mínima; dados de cada corpus são imutáveis."""

import os
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from contracts.models import Chunk, Document, ExperimentRun, Process

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
experiment_runs = Table(
    "experiment_runs",
    metadata,
    Column("run_id", String, primary_key=True),
    Column("payload", JSON, nullable=False),
)
experiment_run_revisions = Table(
    "experiment_run_revisions",
    metadata,
    Column("run_id", String, ForeignKey("experiment_runs.run_id"), primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("payload", JSON, nullable=False),
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
    # Apenas criação inicial. Mudanças de schema exigirão migrações revisadas.
    metadata.create_all(engine)


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


def save_experiment_run(engine: Engine, run: ExperimentRun) -> ExperimentRun:
    """Persiste e relê um registro; repetição idêntica é idempotente."""

    revision = run.parameters.get("revision", 1)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision != 1:
        raise ValueError("A primeira revisão de ExperimentRun deve ser 1.")
    if "revision" not in run.parameters:
        run = run.model_copy(update={"parameters": {**run.parameters, "revision": 1}})
    run_id = str(run.run_id)
    payload = run.model_dump(mode="json")
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                select(experiment_runs.c.payload).where(experiment_runs.c.run_id == run_id)
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(insert(experiment_runs).values(run_id=run_id, payload=payload))
                connection.execute(
                    insert(experiment_run_revisions).values(
                        run_id=run_id, revision=1, payload=payload
                    )
                )
            elif existing != payload:
                raise ValueError("run_id já existe com outro registro experimental.")
            persisted = connection.execute(
                select(experiment_runs.c.payload).where(experiment_runs.c.run_id == run_id)
            ).scalar_one()
    except IntegrityError:
        persisted_run = get_experiment_run(engine, run_id)
        if persisted_run is None or persisted_run.model_dump(mode="json") != payload:
            raise ValueError("run_id já existe com outro registro experimental.") from None
        return persisted_run
    return ExperimentRun.model_validate(persisted)


def update_experiment_run(engine: Engine, run: ExperimentRun) -> ExperimentRun:
    """Acrescenta revisão sequencial sem alterar identidade da execução."""

    run_id = str(run.run_id)
    payload = run.model_dump(mode="json")
    stable_fields = (
        "run_id",
        "process_id",
        "corpus_version",
        "requirements_version",
        "task_id",
        "split",
        "executor",
        "repetition",
        "code_commit",
        "harness_version",
        "adapter_version",
        "model",
        "endpoint_id",
        "prompt_sha256",
    )
    try:
        with engine.begin() as connection:
            previous_payload = connection.execute(
                select(experiment_runs.c.payload).where(experiment_runs.c.run_id == run_id)
            ).scalar_one_or_none()
            if previous_payload is None:
                raise ValueError("Execução ainda não foi registrada.")
            previous = ExperimentRun.model_validate(previous_payload)
            if previous_payload == payload:
                return previous
            if any(getattr(previous, field) != getattr(run, field) for field in stable_fields):
                raise ValueError("A revisão altera a identidade da execução.")
            stable_parameters = (
                "level",
                "max_model_calls",
                "max_tool_calls",
                "timeout_seconds",
                "model_timeout_seconds",
                "backend_timeout_seconds",
            )
            if any(
                previous.parameters.get(key) != run.parameters.get(key) for key in stable_parameters
            ):
                raise ValueError("A revisão altera o protocolo ou orçamento da execução.")
            if (
                run.started_at != previous.started_at
                or run.latency_ms < previous.latency_ms
                or len(run.tool_calls) < len(previous.tool_calls)
                or run.tool_calls[: len(previous.tool_calls)] != previous.tool_calls
                or (
                    previous.input_tokens is not None
                    and (run.input_tokens is None or run.input_tokens < previous.input_tokens)
                )
                or (
                    previous.output_tokens is not None
                    and (run.output_tokens is None or run.output_tokens < previous.output_tokens)
                )
                or run.verified_success != previous.verified_success
                or run.evaluator != previous.evaluator
            ):
                raise ValueError("A revisão reduz métricas ou altera avaliação externa.")
            previous_revision = previous.parameters.get("revision", 1)
            next_revision = run.parameters.get("revision", 0)
            if (
                not isinstance(previous_revision, int)
                or isinstance(previous_revision, bool)
                or not isinstance(next_revision, int)
                or isinstance(next_revision, bool)
            ):
                raise ValueError("Revisão experimental deve ser um inteiro.")
            if next_revision != previous_revision + 1:
                raise ValueError("A revisão experimental não é sequencial.")
            connection.execute(
                insert(experiment_run_revisions).values(
                    run_id=run_id, revision=next_revision, payload=payload
                )
            )
            connection.execute(
                update(experiment_runs)
                .where(experiment_runs.c.run_id == run_id)
                .values(payload=payload)
            )
    except IntegrityError:
        current = get_experiment_run(engine, run_id)
        if current is None or current.model_dump(mode="json") != payload:
            raise ValueError("Conflito concorrente ao atualizar ExperimentRun.") from None
        return current
    return ExperimentRun.model_validate(payload)


def get_experiment_run(engine: Engine, run_id: str) -> ExperimentRun | None:
    with engine.connect() as connection:
        payload = connection.execute(
            select(experiment_runs.c.payload).where(experiment_runs.c.run_id == run_id)
        ).scalar_one_or_none()
    return ExperimentRun.model_validate(payload) if payload is not None else None


def get_experiment_run_revisions(engine: Engine, run_id: str) -> list[ExperimentRun]:
    with engine.connect() as connection:
        rows = (
            connection.execute(
                select(experiment_run_revisions.c.payload)
                .where(experiment_run_revisions.c.run_id == run_id)
                .order_by(experiment_run_revisions.c.revision)
            )
            .scalars()
            .all()
        )
    return [ExperimentRun.model_validate(payload) for payload in rows]

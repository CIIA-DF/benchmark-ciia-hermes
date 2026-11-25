"""Exporta histórico canônico v2 para Evaluation; textos exigem --include-content."""

import argparse
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import ExperimentRun, ToolContext, WriteReceipt
from services.backend.schema import (
    artifacts,
    conversations,
    logical_tool_calls,
    messages,
    runs,
    tool_calls,
)
from services.backend.storage import make_engine
from services.backend.tracking import ToolTracking

EXPORT_VERSION = "2"
# Free-form parameters/text stay behind content opt-in. Never export principal/lease secrets.
EXPERIMENT_FIELDS = (
    "contract_version",
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
    "started_at",
    "latency_ms",
    "tool_calls",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "agent_declared_success",
    "persisted_artifact_ids",
)


def records(
    conn,
    *,
    participant_id=None,
    conversation_id=None,
    run_id=None,
    include_content=False,
    kind="chat",
):
    """Read all evidence in the caller's snapshot; never reconstruct attempts from SSE."""
    if kind not in {"chat", "benchmark", "all"}:
        raise ValueError("Tipo de execução inválido.")
    statement = (
        select(runs, conversations.c.participant_id)
        .outerjoin(conversations, runs.c.conversation_id == conversations.c.conversation_id)
        .order_by(runs.c.created_at, runs.c.run_id)
    )
    if kind != "all":
        statement = statement.where(runs.c.kind == kind)
    if participant_id is not None:
        statement = statement.where(conversations.c.participant_id == str(participant_id))
    if conversation_id is not None:
        statement = statement.where(conversations.c.conversation_id == str(conversation_id))
    if run_id is not None:
        statement = statement.where(runs.c.run_id == str(run_id))
    for row in conn.execute(statement).mappings():
        result = row["result"] or {}
        experiment = result.get("experiment") or {}
        if result.get("experiment") is not None:
            ExperimentRun.model_validate(experiment)
        ToolContext.model_validate(row["context"])
        stored_artifacts = list(
            conn.execute(
                select(artifacts)
                .where(artifacts.c.run_id == row["run_id"])
                .order_by(artifacts.c.artifact_id)
            )
            .mappings()
            .all()
        )
        for artifact in stored_artifacts:
            # Validate without normalizing timestamps or changing the stored receipt.
            WriteReceipt.model_validate(artifact["receipt"])
        item = {
            "export_version": EXPORT_VERSION,
            "participant_id": row["participant_id"],
            "conversation_id": row["conversation_id"],
            "run_id": row["run_id"],
            "kind": row["kind"],
            "executor": row["executor"],
            "context": row["context"],
            "declared": {
                # result_sha256 distinguishes a worker submission from a server timeout.
                "status": result.get("status") if row["result_sha256"] else None,
                "error_code": result.get("error_code") if row["result_sha256"] else None,
                "sources": result.get("sources") if row["result_sha256"] else None,
                "experiment": (
                    {key: experiment.get(key) for key in EXPERIMENT_FIELDS}
                    if result.get("experiment") is not None
                    else None
                ),
            },
            "observed": {
                "status": row["status"],
                "error_code": result.get("error_code"),
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "latency_ms": (
                    (row["finished_at"] - row["started_at"]) * 1000
                    if row["finished_at"] is not None and row["started_at"] is not None
                    else None
                ),
                "task_metadata": {
                    key: row["task_metadata"].get(key) for key in ("task_id", "split", "repetition")
                },
                "logical_calls": [
                    dict(call)
                    for call in conn.execute(
                        select(logical_tool_calls)
                        .where(logical_tool_calls.c.run_id == row["run_id"])
                        .order_by(logical_tool_calls.c.tool_call_id)
                    ).mappings()
                ],
                "physical_attempts": ToolTracking(conn.engine).history(conn, row["run_id"]),
                "legacy_tool_stages": [
                    dict(stage)
                    for stage in conn.execute(
                        select(tool_calls)
                        .where(tool_calls.c.run_id == row["run_id"])
                        .order_by(tool_calls.c.tool_call_id, tool_calls.c.attempt)
                    ).mappings()
                ],
                "artifacts": [
                    {
                        key: artifact[key]
                        for key in (
                            "artifact_id",
                            "run_id",
                            "tool",
                            "idempotency_key",
                            "input_sha256",
                            "receipt",
                        )
                    }
                    for artifact in stored_artifacts
                ],
            },
            # No independent evaluation repository exists in this export's sources.
            "evaluated": {"verified_success": None, "evaluator": None},
            "history_precision": {
                "source": "persisted_history",
                "legacy": "stages_not_physical_requests",
                "total_physical_requests": None,
                "unattributed_attempts_included": False,
            },
        }
        if include_content:
            item["content"] = {
                "task": row["task"],
                "answer": result.get("answer"),
                "messages": [
                    dict(message)
                    for message in conn.execute(
                        select(messages.c.role, messages.c.content)
                        .where(messages.c.run_id == row["run_id"])
                        .order_by(messages.c.created_at, messages.c.message_id)
                    ).mappings()
                ],
                "artifacts": [
                    {"artifact_id": artifact["artifact_id"], "payload": artifact["payload"]}
                    for artifact in stored_artifacts
                ],
                "parameters": experiment.get("parameters"),
            }
        yield item


def export_file(engine, path, **filters):
    """Publish a complete snapshot exclusively; failures never publish a partial destination."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    staging = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".export-",
            suffix=".tmp",
            delete=False,
        ) as target:
            staging = Path(target.name)
            with engine.connect() as connection:
                if engine.dialect.name == "postgresql":
                    connection = connection.execution_options(isolation_level="REPEATABLE READ")
                with connection.begin():
                    # sqlite3 legacy transaction mode does not BEGIN for SELECT by itself.
                    if engine.dialect.name == "sqlite":
                        connection.exec_driver_sql("BEGIN")
                    count = 0
                    for item in records(connection, **filters):
                        target.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
                        count += 1
            target.flush()
            os.fsync(target.fileno())
        # Same-directory hard link publishes atomically without overwriting a racing writer.
        os.link(staging, path)
        return count
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--participant", type=UUID)
    parser.add_argument("--conversation", type=UUID)
    parser.add_argument("--run", type=UUID)
    parser.add_argument("--include-content", action="store_true")
    parser.add_argument("--kind", choices=("chat", "benchmark", "all"), default="chat")
    args = parser.parse_args()
    engine = make_engine()
    try:
        count = export_file(
            engine,
            args.output,
            participant_id=args.participant,
            conversation_id=args.conversation,
            run_id=args.run,
            include_content=args.include_content,
            kind=args.kind,
        )
    except (OSError, SQLAlchemyError, ValueError, TypeError):
        parser.exit(
            1,
            "Exportação não concluída; confira banco e destino privado. "
            "O destino existente não será sobrescrito.\n",
        )
    finally:
        engine.dispose()
    print(f"Exportação concluída: {count} execuções. Preserve o arquivo fora do Git.")


if __name__ == "__main__":
    main()

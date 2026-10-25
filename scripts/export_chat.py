"""Exporta registros locais para Evaluation sem conteúdo textual por padrão."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from services.backend.schema import artifacts, conversations, events, messages, runs
from services.backend.storage import make_engine


def records(conn, *, participant_id=None, conversation_id=None, include_content=False):
    statement = (
        select(runs, conversations.c.participant_id)
        .join(conversations, runs.c.conversation_id == conversations.c.conversation_id)
        .where(runs.c.kind == "chat")
        .order_by(runs.c.created_at, runs.c.run_id)
    )
    if participant_id is not None:
        statement = statement.where(conversations.c.participant_id == str(participant_id))
    if conversation_id is not None:
        statement = statement.where(conversations.c.conversation_id == str(conversation_id))
    for row in conn.execute(statement).mappings():
        result = row["result"] or {}
        experiment = result.get("experiment") or {}
        tool_events = [
            {
                "sequence": event["sequence"],
                "created_at": event["created_at"],
                **{
                    k: event["payload"].get(k)
                    for k in ("tool", "status", "duration_ms", "artifact_id")
                },
            }
            for event in conn.execute(
                select(events)
                .where(events.c.run_id == row["run_id"], events.c.kind == "tool")
                .order_by(events.c.sequence)
            ).mappings()
        ]
        receipts = (
            conn.execute(
                select(artifacts.c.receipt)
                .where(artifacts.c.run_id == row["run_id"])
                .order_by(artifacts.c.artifact_id)
            )
            .scalars()
            .all()
        )
        item = {
            "export_version": "1",
            "participant_id": row["participant_id"],
            "conversation_id": row["conversation_id"],
            "run_id": row["run_id"],
            "kind": row["kind"],
            "executor": row["executor"],
            "context": row["context"],
            "status": row["status"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "latency_ms": (
                (row["finished_at"] - row["started_at"]) * 1000
                if row["finished_at"] is not None and row["started_at"] is not None
                else None
            ),
            "error_code": result.get("error_code"),
            "tool_calls": tool_events,
            "receipts": receipts,
            "sources": result.get("sources", []),
            **{
                key: experiment.get(key)
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "cost_usd",
                    "code_commit",
                    "harness_version",
                    "adapter_version",
                    "model",
                    "endpoint_id",
                    "prompt_sha256",
                )
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
                "artifacts": conn.execute(
                    select(artifacts.c.payload).where(artifacts.c.run_id == row["run_id"])
                )
                .scalars()
                .all(),
            }
        yield item


def export_file(engine, path, **filters):
    # x impede sobrescrita; exportação incompleta nunca é anunciada como concluída.
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin(), Path(path).open("x", encoding="utf-8") as target:
            count = 0
            for item in records(connection, **filters):
                target.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--participant", type=UUID)
    parser.add_argument("--conversation", type=UUID)
    parser.add_argument("--include-content", action="store_true")
    args = parser.parse_args()
    engine = make_engine()
    try:
        count = export_file(
            engine,
            args.output,
            participant_id=args.participant,
            conversation_id=args.conversation,
            include_content=args.include_content,
        )
    except (OSError, SQLAlchemyError):
        parser.exit(
            1,
            "Exportação não concluída; confira banco e destino privado. "
            "Um arquivo parcial pode permanecer; não o use como exportação validada.\n",
        )
    finally:
        engine.dispose()
    print(f"Exportação concluída: {count} execuções. Preserve o arquivo fora do Git.")


if __name__ == "__main__":
    main()

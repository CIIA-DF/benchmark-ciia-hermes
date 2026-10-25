"""Execuções duráveis e transacionais; os workers acessam somente HTTP."""

import hashlib
import json
import os
import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import insert, select, update

from services.backend.auth import authorize, token_hash
from services.backend.corpus import CorpusRepository
from services.backend.errors import fail
from services.backend.schema import (
    artifacts,
    conversations,
    events,
    messages,
    permissions,
    principals,
    requirements,
    runs,
)
from services.backend.storage import processes

TERMINAL = {"succeeded", "failed", "timed_out"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class ExecutionService:
    def __init__(self, engine, corpus=None):
        self.engine = engine
        self.corpus = corpus if corpus is not None else CorpusRepository()
        self.lease_seconds = int(os.getenv("RUN_LEASE_SECONDS", "60"))
        self.context_limit = int(os.getenv("CHAT_CONTEXT_MAX_CHARS", "100000"))
        self.max_run_seconds = int(os.getenv("RUN_TIMEOUT_SECONDS", "300"))
        self.enabled = set(os.getenv("ENABLED_EXECUTORS", "simulation").split(","))
        if min(self.lease_seconds, self.context_limit, self.max_run_seconds) <= 0:
            raise ValueError("Limites de execução devem ser positivos.")

    @contextmanager
    def transaction(self):
        with self.engine.connect() as conn:
            if self.engine.dialect.name == "sqlite":
                conn.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                conn.begin()
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def process(self, conn, context):
        return self.corpus.process(conn, context)

    def operator(self, actor):
        if actor["role"] != "operator":
            fail(403, "forbidden", "Operação restrita ao operador.")

    def check_executor(self, executor):
        if executor not in self.enabled:
            fail(503, "executor_unavailable", "Executor ainda não conectado.")

    def list_processes(self, actor):
        self.operator(actor)
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    select(processes.c.payload)
                    .join(
                        permissions,
                        (processes.c.process_id == permissions.c.process_id)
                        & (processes.c.corpus_version == permissions.c.corpus_version),
                    )
                    .where(permissions.c.principal_id == actor["principal_id"])
                    .order_by(processes.c.process_id, processes.c.corpus_version)
                )
                .scalars()
                .all()
            )

    def create_conversation(self, actor, request):
        self.operator(actor)
        self.check_executor(request.executor)
        values = request.model_dump(mode="json")
        with self.transaction() as conn:
            authorize(conn, actor["principal_id"], request.process_id, request.corpus_version)
            self.process(conn, values)
            row = dict(
                conversation_id=str(uuid4()),
                owner_id=actor["principal_id"],
                created_at=time.time(),
                **values,
            )
            conn.execute(insert(conversations).values(**row))
        return row

    def conversation(self, conn, actor, conversation_id, *, lock=False):
        self.operator(actor)
        stmt = select(conversations).where(
            conversations.c.conversation_id == conversation_id,
            conversations.c.owner_id == actor["principal_id"],
        )
        row = conn.execute(stmt.with_for_update() if lock else stmt).mappings().first()
        if row is None:
            fail(404, "not_found", "Conversa não encontrada.")
        authorize(conn, actor["principal_id"], row["process_id"], row["corpus_version"])
        return dict(row)

    def list_conversations(self, actor, participant_id=None):
        self.operator(actor)
        with self.engine.connect() as conn:
            return [
                dict(r)
                for r in conn.execute(
                    select(conversations)
                    .join(
                        permissions,
                        (conversations.c.process_id == permissions.c.process_id)
                        & (conversations.c.corpus_version == permissions.c.corpus_version)
                        & (permissions.c.principal_id == actor["principal_id"]),
                    )
                    .where(
                        conversations.c.owner_id == actor["principal_id"],
                        conversations.c.participant_id == str(participant_id)
                        if participant_id is not None
                        else True,
                    )
                    .order_by(conversations.c.created_at.desc())
                    .limit(100)
                ).mappings()
            ]

    def get_conversation(self, actor, conversation_id):
        self.expire()
        with self.engine.connect() as conn:
            row = self.conversation(conn, actor, conversation_id)
            row["runs"] = [
                self.public_run(conn, dict(r))
                for r in conn.execute(
                    select(runs)
                    .where(runs.c.conversation_id == conversation_id)
                    .order_by(runs.c.created_at)
                ).mappings()
            ]
            # Runs são lidos antes das mensagens; a resposta só aparece se o snapshot do run
            # já estiver concluído, pois ambos são gravados na mesma transação de finish.
            status = {run["run_id"]: run["status"] for run in row["runs"]}
            row["messages"] = [
                dict(r)
                for r in conn.execute(
                    select(messages)
                    .where(messages.c.conversation_id == conversation_id)
                    .order_by(messages.c.created_at, messages.c.message_id)
                ).mappings()
                if r["run_id"] in status
                and (r["role"] != "assistant" or status[r["run_id"]] == "succeeded")
            ]
        return row

    def event(self, conn, run_id, kind, payload, event_id=None):
        sequence = (
            conn.execute(select(runs.c.event_sequence).where(runs.c.run_id == run_id)).scalar_one()
            + 1
        )
        conn.execute(update(runs).where(runs.c.run_id == run_id).values(event_sequence=sequence))
        conn.execute(
            insert(events).values(
                run_id=run_id,
                sequence=sequence,
                event_id=event_id or str(uuid4()),
                kind=kind,
                payload=payload,
                created_at=time.time(),
            )
        )
        return sequence

    def create_run(self, actor, request, conversation_id=None):
        self.operator(actor)
        self.expire()
        raw = request.model_dump(mode="json")
        hashed = digest({"conversation_id": conversation_id, **raw})
        with self.transaction() as conn:
            # Serializa reenvios do mesmo operador, inclusive antes de inserir o run.
            conn.execute(
                select(principals)
                .where(principals.c.principal_id == actor["principal_id"])
                .with_for_update()
            ).first()
            previous = (
                conn.execute(
                    select(runs).where(
                        runs.c.owner_id == actor["principal_id"],
                        runs.c.idempotency_key == request.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if previous:
                authorize(
                    conn,
                    actor["principal_id"],
                    previous["context"]["process_id"],
                    previous["context"]["corpus_version"],
                )
                if previous["input_sha256"] != hashed:
                    fail(409, "idempotency_conflict", "Chave reutilizada com outra entrada.")
                return self.public_run(conn, dict(previous))
            history = []
            if conversation_id:
                conversation = self.conversation(conn, actor, conversation_id, lock=True)
                active = conn.execute(
                    select(runs.c.run_id).where(
                        runs.c.conversation_id == conversation_id,
                        runs.c.status.in_(["queued", "running"]),
                    )
                ).first()
                if active:
                    fail(409, "conflict", "Aguarde a execução ativa desta conversa.")
                context = {
                    k: conversation[k]
                    for k in ("process_id", "corpus_version", "requirements_version")
                }
                executor = conversation["executor"]
                history = [
                    dict(r)
                    for r in conn.execute(
                        select(messages.c.role, messages.c.content)
                        .join(runs, messages.c.run_id == runs.c.run_id)
                        .where(
                            messages.c.conversation_id == conversation_id,
                            runs.c.status == "succeeded",
                        )
                        .order_by(messages.c.created_at, messages.c.message_id)
                    ).mappings()
                ]
                task = request.content
                task_metadata = {
                    "task_id": f"chat:{uuid4()}",
                    "split": "development",
                    "repetition": 1,
                }
            else:
                context = {
                    k: raw[k] for k in ("process_id", "corpus_version", "requirements_version")
                }
                executor, task = request.executor, request.task
                task_metadata = {k: raw[k] for k in ("task_id", "split", "repetition")}
            self.check_executor(executor)
            authorize(conn, actor["principal_id"], context["process_id"], context["corpus_version"])
            self.process(conn, context)
            history.append({"role": "user", "content": task})
            if sum(len(m["content"]) for m in history) > self.context_limit:
                fail(422, "context_limit", "Limite de contexto atingido; inicie nova conversa.")
            now, run_id = time.time(), str(uuid4())
            context["run_id"] = run_id
            row = dict(
                run_id=run_id,
                owner_id=actor["principal_id"],
                conversation_id=conversation_id,
                idempotency_key=request.idempotency_key,
                input_sha256=hashed,
                kind="chat" if conversation_id else "benchmark",
                executor=executor,
                status="queued",
                context=context,
                history=history,
                task=task,
                task_metadata=task_metadata,
                created_at=now,
                event_sequence=0,
            )
            conn.execute(insert(runs).values(**row))
            if conversation_id:
                conn.execute(
                    insert(messages).values(
                        message_id=str(uuid4()),
                        conversation_id=conversation_id,
                        run_id=run_id,
                        role="user",
                        content=task,
                        created_at=now,
                    )
                )
            self.event(conn, run_id, "status", {"status": "queued", "text": "Aguardando agente"})
            return self.public_run(conn, row)

    def expire(self):
        now = time.time()
        with self.transaction() as conn:
            expired = (
                conn.execute(
                    select(runs)
                    .where(
                        runs.c.status == "running",
                        (runs.c.lease_until <= now)
                        | (runs.c.started_at + self.max_run_seconds <= now),
                    )
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for row in expired:
                conn.execute(
                    update(runs)
                    .where(runs.c.run_id == row["run_id"])
                    .values(
                        status="timed_out",
                        finished_at=now,
                        result={"status": "timed_out", "error_code": "worker_timeout"},
                    )
                )
                self.event(conn, row["run_id"], "done", {"status": "timed_out"})

    def claim(self, actor, executor, run_id=None):
        if actor["role"] != "worker" or actor["executor"] != executor:
            fail(403, "forbidden", "Worker incompatível com o executor.")
        self.check_executor(executor)
        self.expire()
        with self.transaction() as conn:
            # Permissões dos workers também são limitadas a processo e corpus.
            statement = (
                select(runs)
                .where(runs.c.status == "queued", runs.c.executor == executor)
                .order_by(runs.c.created_at)
                .with_for_update(skip_locked=True)
            )
            if run_id is not None:
                statement = statement.where(runs.c.run_id == str(run_id))
            candidates = conn.execute(statement).mappings()
            for candidate in candidates:
                context = candidate["context"]
                worker_grant = conn.execute(
                    select(permissions).where(
                        permissions.c.principal_id == actor["principal_id"],
                        permissions.c.process_id == context["process_id"],
                        permissions.c.corpus_version == context["corpus_version"],
                    )
                ).first()
                owner_grant = conn.execute(
                    select(permissions).where(
                        permissions.c.principal_id == candidate["owner_id"],
                        permissions.c.process_id == context["process_id"],
                        permissions.c.corpus_version == context["corpus_version"],
                    )
                ).first()
                if not worker_grant or not owner_grant:
                    continue
                lease = secrets.token_urlsafe(32)
                now = time.time()
                conn.execute(
                    update(runs)
                    .where(runs.c.run_id == candidate["run_id"])
                    .values(
                        status="running",
                        worker_id=actor["principal_id"],
                        lease_sha256=token_hash(lease),
                        lease_until=now + self.lease_seconds,
                        started_at=now,
                    )
                )
                self.event(
                    conn,
                    candidate["run_id"],
                    "status",
                    {"status": "running", "text": "Agente conectado"},
                )
                return {
                    "run_id": candidate["run_id"],
                    "context": context,
                    "history": candidate["history"],
                    "task": candidate["task"],
                    "task_metadata": candidate["task_metadata"],
                    "kind": candidate["kind"],
                    "executor": executor,
                    "run_token": lease,
                    "lease_seconds": self.lease_seconds,
                    "heartbeat_seconds": max(1, self.lease_seconds // 4),
                }
        return None

    def worker_run(self, conn, actor, run_id, lease, *, terminal=False):
        row = (
            conn.execute(select(runs).where(runs.c.run_id == str(run_id)).with_for_update())
            .mappings()
            .first()
        )
        if (
            row is None
            or actor["role"] != "worker"
            or row["worker_id"] != actor["principal_id"]
            or not lease
            or not secrets.compare_digest(row["lease_sha256"] or "", token_hash(lease))
        ):
            fail(403, "forbidden", "Worker não autorizado para esta execução.")
        if row["status"] != "running":
            if not terminal or row["status"] not in TERMINAL:
                fail(409, "conflict", "Execução não está ativa.")
        elif (
            row["lease_until"] <= time.time()
            or row["started_at"] + self.max_run_seconds <= time.time()
        ):
            fail(409, "conflict", "Reserva da execução expirada.")
        authorize(
            conn,
            actor["principal_id"],
            row["context"]["process_id"],
            row["context"]["corpus_version"],
        )
        authorize(
            conn, row["owner_id"], row["context"]["process_id"], row["context"]["corpus_version"]
        )
        return dict(row)

    def heartbeat(self, actor, run_id, lease):
        with self.transaction() as conn:
            self.worker_run(conn, actor, run_id, lease)
            conn.execute(
                update(runs)
                .where(runs.c.run_id == str(run_id))
                .values(lease_until=time.time() + self.lease_seconds)
            )
        return {"status": "running"}

    def add_event(self, actor, run_id, lease, value):
        raw = value.model_dump(mode="json")
        with self.transaction() as conn:
            self.worker_run(conn, actor, run_id, lease)
            previous = (
                conn.execute(
                    select(events).where(
                        events.c.run_id == str(run_id), events.c.event_id == raw["event_id"]
                    )
                )
                .mappings()
                .first()
            )
            payload = {"text": value.text}
            if previous:
                if previous["kind"] != value.kind or previous["payload"] != payload:
                    fail(409, "idempotency_conflict", "Evento reutilizado com outro conteúdo.")
                return {"sequence": previous["sequence"]}
            if value.kind == "text_delta":
                if len(self.partial(conn, run_id)) + len(value.text) > 100_000:
                    fail(422, "context_limit", "Resposta excedeu o limite do contrato.")
            seq = self.event(conn, str(run_id), value.kind, payload, raw["event_id"])
        return {"sequence": seq}

    def partial(self, conn, run_id, upto=None):
        statement = select(events.c.payload).where(
            events.c.run_id == str(run_id), events.c.kind == "text_delta"
        )
        if upto is not None:
            statement = statement.where(events.c.sequence <= upto)
        return "".join(
            row["text"] for row in conn.execute(statement.order_by(events.c.sequence)).scalars()
        )

    def validate_sources(self, conn, context, sources):
        self.corpus.validate_sources(conn, context, sources)

    def finish(self, actor, run_id, lease, value):
        raw = value.model_dump(mode="json")
        hashed = digest(raw)
        with self.transaction() as conn:
            row = self.worker_run(conn, actor, run_id, lease, terminal=True)
            if row["status"] in TERMINAL:
                if row["result_sha256"] != hashed:
                    fail(409, "idempotency_conflict", "Resultado já encerrado ou diferente.")
                return self.public_run(conn, row)
            self.validate_sources(conn, row["context"], value.sources)
            partial = self.partial(conn, run_id)
            if value.status == "succeeded" and (
                not value.answer.strip()
                or (partial and partial != value.answer)
                or value.error_code is not None
            ):
                fail(422, "validation_error", "Resposta final inconsistente com o streaming.")
            if value.experiment:
                report = value.experiment
                if (
                    report.model_dump(mode="json", include=set(row["context"])) != row["context"]
                    or report.executor != row["executor"]
                    or report.verified_success is not None
                    or report.evaluator is not None
                    or any(getattr(report, k) != v for k, v in row["task_metadata"].items())
                ):
                    fail(422, "validation_error", "Registro experimental incompatível.")
                existing_ids = set(
                    conn.execute(
                        select(artifacts.c.artifact_id).where(artifacts.c.run_id == str(run_id))
                    ).scalars()
                )
                if not set(report.persisted_artifact_ids) <= existing_ids:
                    fail(422, "validation_error", "Artefato não pertence à execução.")
            if row["kind"] == "benchmark" and value.status == "succeeded" and not value.experiment:
                fail(422, "validation_error", "Benchmark exige registro experimental.")
            now = time.time()
            conn.execute(
                update(runs)
                .where(runs.c.run_id == str(run_id))
                .values(status=value.status, result=raw, result_sha256=hashed, finished_at=now)
            )
            if row["conversation_id"] and value.status == "succeeded":
                conn.execute(
                    insert(messages).values(
                        message_id=str(uuid4()),
                        conversation_id=row["conversation_id"],
                        run_id=str(run_id),
                        role="assistant",
                        content=value.answer,
                        created_at=now,
                    )
                )
            self.event(conn, str(run_id), "done", {"status": value.status})
            row.update(status=value.status, result=raw, finished_at=now)
            return self.public_run(conn, row)

    def public_run(self, conn, row):
        # Cursor, status e resultado vêm de uma única leitura da linha; o texto parcial é
        # limitado a essa sequência. Deltas confirmados depois chegam pelo SSE após o cursor,
        # sem perda nem duplicação e sem travar o worker.
        row = dict(
            conn.execute(select(runs).where(runs.c.run_id == row["run_id"])).mappings().one()
        )
        cursor = row["event_sequence"]
        return {
            k: row.get(k)
            for k in (
                "run_id",
                "conversation_id",
                "kind",
                "executor",
                "status",
                "context",
                "created_at",
                "started_at",
                "finished_at",
                "result",
            )
        } | {
            "artifacts": [
                dict(r)
                for r in conn.execute(
                    select(artifacts.c.artifact_id, artifacts.c.tool)
                    .where(artifacts.c.run_id == row["run_id"])
                    .order_by(artifacts.c.artifact_id)
                ).mappings()
            ],
            "partial_answer": self.partial(conn, row["run_id"], upto=cursor),
            "last_event_id": cursor,
        }

    def owned_run(self, conn, actor, run_id):
        self.operator(actor)
        row = (
            conn.execute(
                select(runs).where(
                    runs.c.run_id == str(run_id), runs.c.owner_id == actor["principal_id"]
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            fail(404, "not_found", "Execução não encontrada.")
        authorize(
            conn,
            actor["principal_id"],
            row["context"]["process_id"],
            row["context"]["corpus_version"],
        )
        return dict(row)

    def get_run(self, actor, run_id):
        self.expire()
        with self.engine.connect() as conn:
            return self.public_run(conn, self.owned_run(conn, actor, run_id))

    def read_events(self, actor, run_id, after):
        self.expire()
        with self.engine.connect() as conn:
            row = self.owned_run(conn, actor, run_id)
            items = [
                dict(r)
                for r in conn.execute(
                    select(events)
                    .where(events.c.run_id == str(run_id), events.c.sequence > after)
                    .order_by(events.c.sequence)
                    .limit(100)
                ).mappings()
            ]
            return items, row["status"]

    def tool_context(self, conn, actor, context, lease, *, write=False):
        raw = context.model_dump(
            mode="json", include={"run_id", "process_id", "corpus_version", "requirements_version"}
        )
        row = self.worker_run(conn, actor, context.run_id, lease)
        if raw != row["context"]:
            fail(403, "forbidden", "Contexto diferente da execução autenticada.")
        if write:
            owner = (
                conn.execute(select(principals).where(principals.c.principal_id == row["owner_id"]))
                .mappings()
                .one()
            )
            if not owner["can_write"] or not actor["can_write"]:
                fail(403, "forbidden", "Perfil sem permissão de escrita.")
        self.process(conn, raw)
        return row

    def write_artifact(self, actor, query, lease, tool):
        raw = query.model_dump(mode="json")
        hashed = digest(raw)
        with self.transaction() as conn:
            row = self.tool_context(conn, actor, query, lease, write=True)
            self.validate_sources(conn, row["context"], query.evidence)
            if tool == "registrar_pendencia":
                exists = conn.execute(
                    select(requirements.c.requirement_id).where(
                        requirements.c.process_id == query.process_id,
                        requirements.c.corpus_version == query.corpus_version,
                        requirements.c.requirements_version == query.requirements_version,
                        requirements.c.requirement_id == query.requirement_id,
                    )
                ).first()
                if not exists:
                    fail(422, "validation_error", "Requisito não pertence ao checklist versionado.")
            prior = (
                conn.execute(
                    select(artifacts).where(
                        artifacts.c.run_id == str(query.run_id),
                        artifacts.c.tool == tool,
                        artifacts.c.idempotency_key == query.idempotency_key,
                    )
                )
                .mappings()
                .first()
            )
            if prior:
                if prior["input_sha256"] != hashed:
                    fail(409, "idempotency_conflict", "Chave reutilizada com outro conteúdo.")
                return {**prior["receipt"], "replayed": True}
            artifact_id = str(uuid4())
            receipt = {
                **row["context"],
                "artifact_id": artifact_id,
                "persisted_at": datetime.now(UTC).isoformat(),
                "content_sha256": hashlib.sha256(query.content.encode()).hexdigest(),
                "replayed": False,
            }
            conn.execute(
                insert(artifacts).values(
                    artifact_id=artifact_id,
                    run_id=str(query.run_id),
                    tool=tool,
                    idempotency_key=query.idempotency_key,
                    input_sha256=hashed,
                    payload=raw,
                    receipt=receipt,
                )
            )
            self.event(
                conn,
                str(query.run_id),
                "tool",
                {"tool": tool, "status": "ok", "artifact_id": artifact_id},
            )
        # Leitura independente da transação que confirmou a gravação.
        with self.engine.connect() as conn:
            return conn.execute(
                select(artifacts.c.receipt).where(artifacts.c.artifact_id == artifact_id)
            ).scalar_one()

    def get_artifact(self, actor, artifact_id):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(artifacts).where(artifacts.c.artifact_id == artifact_id))
                .mappings()
                .first()
            )
            if row is None:
                fail(404, "not_found", "Artefato não encontrado.")
            self.owned_run(conn, actor, row["run_id"])
            return {
                "artifact_id": artifact_id,
                "tool": row["tool"],
                "payload": row["payload"],
                "receipt": row["receipt"],
            }

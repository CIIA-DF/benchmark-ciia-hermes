"""Execuções duráveis e transacionais; os workers acessam somente HTTP."""

import hashlib
import os
import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection, RowMapping

from contracts.models import ArtifactResponse, Process, Requirement, ToolContext
from services.backend.artifact_integrity import validate_artifact
from services.backend.auth import authenticate, authorize, token_hash
from services.backend.corpus import CorpusRepository
from services.backend.errors import ToolFailure, fail
from services.backend.hashing import digest
from services.backend.result_integrity import validate_experiment_history
from services.backend.schema import (
    artifacts,
    conversations,
    events,
    logical_tool_calls,
    messages,
    permissions,
    physical_tool_attempts,
    principals,
    requirements,
    runs,
    stream_leases,
    tool_calls,
    worker_presence,
)
from services.backend.storage import processes
from services.backend.tracking import ToolTracking

TERMINAL = {"succeeded", "failed", "timed_out"}
MAX_EVENTS_PER_RUN = 20_000
MAX_SSE_CONNECTIONS = 5
SSE_LEASE_SECONDS = 30.0
WORKER_FRESHNESS_SECONDS = 60.0
MAX_PHYSICAL_ATTEMPTS_PER_RUN = 1_000


class EventLimitReached(ToolFailure):
    """Roll back the attempted operation before recording a durable terminal outcome."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        super().__init__(429, "resource_limit", "Limite de eventos da execução atingido.", run_id)


class ExecutionService:
    def __init__(self, engine, corpus=None):
        self.engine = engine
        self.tracking = ToolTracking(engine)
        self.corpus = corpus if corpus is not None else CorpusRepository()
        self.lease_seconds = int(os.getenv("RUN_LEASE_SECONDS", "60"))
        self.context_limit = int(os.getenv("CHAT_CONTEXT_MAX_CHARS", "100000"))
        self.max_run_seconds = int(os.getenv("RUN_TIMEOUT_SECONDS", "300"))
        self.queue_timeout_seconds = int(os.getenv("RUN_QUEUE_TIMEOUT_SECONDS", "300"))
        self.max_queued_per_operator = int(os.getenv("RUN_MAX_QUEUED_PER_OPERATOR", "20"))
        self.enabled = set(os.getenv("ENABLED_EXECUTORS", "simulation").split(","))
        # Chamadas lógicas de tool por run; 0 mantém sem limite até a decisão da Metodologia.
        self.max_tool_calls = int(os.getenv("RUN_MAX_TOOL_CALLS", "0"))
        if (
            min(
                self.lease_seconds,
                self.context_limit,
                self.max_run_seconds,
                self.queue_timeout_seconds,
                self.max_queued_per_operator,
            )
            <= 0
        ):
            raise ValueError("Limites de execução devem ser positivos.")
        if self.max_tool_calls < 0:
            raise ValueError("RUN_MAX_TOOL_CALLS não pode ser negativo.")

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
            except EventLimitReached as exc:
                conn.rollback()
                # The rejected operation (including artifact effects) must not commit.
                # Reacquire the run lock and preserve any terminal outcome that won the race.
                # Reuse this connection: recovery must work even with a one-slot pool.
                if self.engine.dialect.name == "sqlite":
                    conn.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    conn.begin()
                try:
                    row = (
                        conn.execute(
                            select(runs).where(runs.c.run_id == exc.run_id).with_for_update()
                        )
                        .mappings()
                        .one()
                    )
                    self.end_event_limit(conn, row)
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
                raise
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

    def capabilities(self, actor):
        self.operator(actor)
        worker_grant = permissions.alias("worker_grant")
        operator_grant = permissions.alias("operator_grant")
        now = time.time()
        with self.engine.connect() as conn:
            observed = dict(
                conn.execute(
                    select(worker_presence.c.executor, func.max(worker_presence.c.observed_at))
                    .join(principals, principals.c.principal_id == worker_presence.c.principal_id)
                    .join(worker_grant, worker_grant.c.principal_id == principals.c.principal_id)
                    .join(
                        operator_grant,
                        and_(
                            operator_grant.c.principal_id == actor["principal_id"],
                            operator_grant.c.process_id == worker_grant.c.process_id,
                            operator_grant.c.corpus_version == worker_grant.c.corpus_version,
                        ),
                    )
                    .where(
                        principals.c.role == "worker",
                        principals.c.executor == worker_presence.c.executor,
                        worker_presence.c.observed_at <= now,
                    )
                    .group_by(worker_presence.c.executor)
                ).all()
            )
        return {
            "executors": [
                {
                    "name": name,
                    "available": name in self.enabled,
                    "enabled": name in self.enabled,
                    "simulation": name == "simulation",
                    "worker_recent": name in observed
                    and now - observed[name] <= WORKER_FRESHNESS_SECONDS,
                    "last_seen_at": observed.get(name),
                    # API environment does not attest the configuration of a remote worker.
                    "model": None,
                    "configuration_known": False,
                }
                for name in ("simulation", "hermes", "langgraph")
            ],
            "can_write": actor["can_write"],
            "profile": actor["principal_id"],
        }

    def list_processes(self, actor):
        self.operator(actor)
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(processes.c.process_id, processes.c.corpus_version, processes.c.payload)
                .join(
                    permissions,
                    (processes.c.process_id == permissions.c.process_id)
                    & (processes.c.corpus_version == permissions.c.corpus_version),
                )
                .where(permissions.c.principal_id == actor["principal_id"])
                .order_by(processes.c.process_id, processes.c.corpus_version)
            ).mappings()
            result = []
            for row in rows:
                try:
                    process = Process.model_validate(row["payload"])
                    if (process.process_id, process.corpus_version) != (
                        row["process_id"],
                        row["corpus_version"],
                    ):
                        raise ValueError("Stored process identity differs from authorized row")
                except (ValidationError, ValueError):
                    fail(500, "invalid_response", "Metadados do processo inconsistentes.")
                result.append(process.model_dump(mode="json"))
            return result

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
        if kind != "done" and sequence >= MAX_EVENTS_PER_RUN:
            raise EventLimitReached(run_id)
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

    def end_event_limit(self, conn, row):
        """Caller holds the run lock; one reserved terminal event survives the limit."""
        if row["status"] in TERMINAL:
            return
        conn.execute(
            update(runs)
            .where(runs.c.run_id == row["run_id"])
            .values(
                status="failed",
                finished_at=time.time(),
                result={"status": "failed", "error_code": "event_limit"},
            )
        )
        self.event(conn, row["run_id"], "done", {"status": "failed", "error_code": "event_limit"})

    def ensure_queue_capacity(self, conn: Connection, principal_id: str) -> None:
        """Caller holds the operator lock (BEGIN IMMEDIATE on SQLite)."""
        # Recheck under the operator lock if the initial maintenance pass crossed a deadline.
        now = time.time()
        expired = (
            conn.execute(
                select(runs)
                .where(
                    runs.c.owner_id == principal_id,
                    runs.c.status == "queued",
                    runs.c.created_at <= now - self.queue_timeout_seconds,
                )
                .with_for_update(skip_locked=True)
            )
            .mappings()
            .all()
        )
        for row in expired:
            self._timeout_run(conn, row, now, "queue_timeout")
        queued = conn.execute(
            select(func.count())
            .select_from(runs)
            .where(runs.c.owner_id == principal_id, runs.c.status == "queued")
        ).scalar_one()
        if queued >= self.max_queued_per_operator:
            fail(
                429,
                "resource_limit",
                "Limite de execuções em fila atingido para o operador.",
                retryable=True,
            )

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
            # Both queue producers share the operator lock and capacity check.
            self.ensure_queue_capacity(conn, actor["principal_id"])
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

    def _timeout_run(
        self,
        conn: Connection,
        row: RowMapping,
        now: float,
        cause: Literal["queue_timeout", "worker_timeout"],
    ) -> None:
        """Caller holds the run lock; terminal state and event commit together."""
        conn.execute(
            update(runs)
            .where(runs.c.run_id == row["run_id"])
            .values(
                status="timed_out",
                finished_at=now,
                result={"status": "timed_out", "error_code": cause},
            )
        )
        payload = {"status": "timed_out"}
        if cause == "queue_timeout":
            payload["error_code"] = cause
        self.event(conn, row["run_id"], "done", payload)

    def expire(self):
        now = time.time()
        with self.transaction() as conn:
            expired = (
                conn.execute(
                    select(runs)
                    .where(
                        or_(
                            and_(
                                runs.c.status == "queued",
                                runs.c.created_at <= now - self.queue_timeout_seconds,
                            ),
                            and_(
                                runs.c.status == "running",
                                (runs.c.lease_until <= now)
                                | (runs.c.started_at + self.max_run_seconds <= now),
                            ),
                        )
                    )
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .all()
            )
            for row in expired:
                cause = "queue_timeout" if row["status"] == "queued" else "worker_timeout"
                self._timeout_run(conn, row, now, cause)

    def observe_worker(self, conn, actor, executor, source: Literal["claim", "heartbeat"]):
        """Lock the current identity before writing an observed presence timestamp."""
        current = (
            conn.execute(
                select(principals)
                .where(principals.c.principal_id == actor["principal_id"])
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if (
            current is None
            or current["role"] != "worker"
            or current["executor"] != executor
            or current["token_sha256"] != actor["token_sha256"]
        ):
            fail(403, "forbidden", "Worker incompatível com o executor.")
        values = dict(executor=executor, observed_at=time.time(), source=source)
        exists = conn.execute(
            select(worker_presence.c.principal_id).where(
                worker_presence.c.principal_id == actor["principal_id"]
            )
        ).first()
        if exists:
            conn.execute(
                update(worker_presence)
                .where(worker_presence.c.principal_id == actor["principal_id"])
                .values(**values)
            )
        else:
            conn.execute(
                insert(worker_presence).values(principal_id=actor["principal_id"], **values)
            )

    def claim(self, actor, executor, run_id=None):
        if actor["role"] != "worker" or actor["executor"] != executor:
            fail(403, "forbidden", "Worker incompatível com o executor.")
        self.check_executor(executor)
        self.expire()
        with self.transaction() as conn:
            self.observe_worker(conn, actor, executor, "claim")
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
                # The candidate may have expired after the initial maintenance pass.
                if candidate["created_at"] + self.queue_timeout_seconds <= now:
                    self._timeout_run(conn, candidate, now, "queue_timeout")
                    continue
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
            or actor["executor"] != row["executor"]
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

    def admit_physical_tool_request(
        self,
        attempt_id: str,
        authorization: str | None,
        lease: str | None,
        tool_call_id: str | None,
    ) -> bool:
        """Bind before reading HTTP bodies; never discard denials from the audit trail."""
        try:
            actor = authenticate(self.engine, authorization)
        except ToolFailure:
            return True  # Authentication/validation handlers retain their public behavior.
        with self.transaction() as conn:
            row = self.lease_run(conn, actor, lease)
            if row is None:
                return True  # Untrusted body run IDs cannot attribute a physical request.
            conn.execute(
                update(physical_tool_attempts)
                .where(physical_tool_attempts.c.attempt_id == attempt_id)
                .values(run_id=row["run_id"], tool_call_id=tool_call_id)
            )
            used = conn.execute(
                select(func.count())
                .select_from(physical_tool_attempts)
                .where(physical_tool_attempts.c.run_id == row["run_id"])
            ).scalar_one()
            return used <= MAX_PHYSICAL_ATTEMPTS_PER_RUN

    def heartbeat(self, actor, run_id, lease):
        with self.transaction() as conn:
            row = self.worker_run(conn, actor, run_id, lease)
            self.observe_worker(conn, actor, row["executor"], "heartbeat")
            # Recheck grants after acquiring the current worker profile lock.
            for principal_id in (actor["principal_id"], row["owner_id"]):
                authorize(
                    conn,
                    principal_id,
                    row["context"]["process_id"],
                    row["context"]["corpus_version"],
                )
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
                validate_experiment_history(conn, row, report)
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

    def stream_operator(self, conn, actor):
        self.operator(actor)
        current = (
            conn.execute(
                select(principals)
                .where(principals.c.principal_id == actor["principal_id"])
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if (
            current is None
            or current["role"] != "operator"
            or current["token_sha256"] != actor["token_sha256"]
        ):
            fail(403, "forbidden", "Operador não autorizado para o fluxo.")

    def open_stream(self, actor, run_id):
        with self.transaction() as conn:
            self.stream_operator(conn, actor)
            self.owned_run(conn, actor, run_id)
            now = time.time()
            conn.execute(
                delete(stream_leases).where(
                    stream_leases.c.principal_id == actor["principal_id"],
                    stream_leases.c.lease_until <= now,
                )
            )
            used = conn.execute(
                select(func.count())
                .select_from(stream_leases)
                .where(
                    stream_leases.c.principal_id == actor["principal_id"],
                )
            ).scalar_one()
            if used >= MAX_SSE_CONNECTIONS:
                fail(
                    429,
                    "resource_limit",
                    "Limite de conexões SSE do operador atingido.",
                    retryable=True,
                )
            lease_id = str(uuid4())
            conn.execute(
                insert(stream_leases).values(
                    lease_id=lease_id,
                    principal_id=actor["principal_id"],
                    run_id=str(run_id),
                    lease_until=now + SSE_LEASE_SECONDS,
                )
            )
        return lease_id

    def renew_stream(self, actor, run_id, lease_id):
        with self.transaction() as conn:
            self.stream_operator(conn, actor)
            self.owned_run(conn, actor, run_id)
            now = time.time()
            row = (
                conn.execute(
                    select(stream_leases).where(
                        stream_leases.c.lease_id == lease_id,
                        stream_leases.c.principal_id == actor["principal_id"],
                        stream_leases.c.run_id == str(run_id),
                        stream_leases.c.lease_until > now,
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                fail(409, "conflict", "Reserva do fluxo expirada.")
            if row["lease_until"] <= now + SSE_LEASE_SECONDS / 2:
                conn.execute(
                    update(stream_leases)
                    .where(stream_leases.c.lease_id == lease_id)
                    .values(lease_until=now + SSE_LEASE_SECONDS)
                )

    def close_stream(self, lease_id):
        with self.transaction() as conn:
            conn.execute(delete(stream_leases).where(stream_leases.c.lease_id == lease_id))

    def authorize_tool_context(self, conn, actor, context, lease, *, write=False):
        raw = context.model_dump(
            mode="json", include={"run_id", "process_id", "corpus_version", "requirements_version"}
        )
        row = self.worker_run(conn, actor, context.run_id, lease)
        if raw != row["context"]:
            fail(403, "forbidden", "Contexto diferente da execução autenticada.")
        if write:
            # Re-read both authorities in this transaction, never the cached actor.
            # Deterministic row locks serialize profile changes until the effect commits.
            profiles = {}
            for principal_id in sorted({row["owner_id"], row["worker_id"]}):
                profile = (
                    conn.execute(
                        select(principals)
                        .where(principals.c.principal_id == principal_id)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if profile is None:
                    fail(403, "forbidden", "Perfil sem permissao de escrita.")
                profiles[principal_id] = profile
            owner, worker = profiles[row["owner_id"]], profiles[row["worker_id"]]
            if (
                owner["role"] != "operator"
                or worker["role"] != "worker"
                or worker["executor"] != row["executor"]
                or not owner["can_write"]
                or not worker["can_write"]
            ):
                fail(403, "forbidden", "Perfil sem permissão de escrita.")
            # Provisioning also locks the principal before replacing its grants.
            # Recheck grants after any wait for those locks, using current data.
            for principal_id in sorted(profiles):
                authorize(conn, principal_id, raw["process_id"], raw["corpus_version"])
        return row

    def tool_context(self, conn, actor, context, lease, call, *, write=False):
        # Domain access belongs only to the effect transaction, after durable binding.
        row = self.authorize_tool_context(conn, actor, context, lease, write=write)
        self.process(conn, row["context"])
        return row

    def reserve_tool_call(self, conn, run_id, call):
        self.tracking.bind(conn, run_id, call)
        # Caller holds the run lock. This transaction commits before the effect:
        # rollback/crash cannot free an ID for a different operation.
        known = (
            conn.execute(
                select(logical_tool_calls).where(
                    logical_tool_calls.c.run_id == run_id,
                    logical_tool_calls.c.tool_call_id == call["tool_call_id"],
                )
            )
            .mappings()
            .first()
        )
        if known:
            if (known["tool"], known["args_sha256"]) != (call["tool"], call["args_sha256"]):
                fail(409, "idempotency_conflict", "Identificador de chamada reutilizado.")
            return
        used = conn.execute(
            select(func.count())
            .select_from(logical_tool_calls)
            .where(logical_tool_calls.c.run_id == run_id)
        ).scalar_one()
        if self.max_tool_calls and used >= self.max_tool_calls:
            fail(409, "budget_exceeded", "Orcamento de chamadas esgotado nesta execucao.")
        conn.execute(
            insert(logical_tool_calls).values(
                run_id=run_id,
                tool_call_id=call["tool_call_id"],
                tool=call["tool"],
                args_sha256=call["args_sha256"],
            )
        )

    def tool_attempt(
        self,
        conn,
        run_id,
        call,
        status,
        *,
        code=None,
        replayed=False,
        artifact_id=None,
        notify=True,
    ):
        """Grava uma tentativa e, com o run ativo, avisa o acompanhamento."""
        attempt = (
            conn.execute(
                select(func.coalesce(func.max(tool_calls.c.attempt), 0)).where(
                    tool_calls.c.run_id == run_id,
                    tool_calls.c.tool_call_id == call["tool_call_id"],
                )
            ).scalar_one()
            + 1
        )
        duration = (time.perf_counter() - call["clock"]) * 1000
        conn.execute(
            insert(tool_calls).values(
                run_id=run_id,
                tool_call_id=call["tool_call_id"],
                attempt=attempt,
                tool=call["tool"],
                started_at=call["started_at"],
                duration_ms=duration,
                http_status=status,
                code=code,
                replayed=replayed,
                artifact_id=artifact_id,
                args_sha256=call["args_sha256"],
            )
        )
        if status == 200 and artifact_id is not None:
            self.tracking.effect(conn, call, artifact_id, replayed)
        if notify:
            sequence = conn.execute(
                select(runs.c.event_sequence).where(runs.c.run_id == run_id)
            ).scalar_one()
            if status >= 400 and sequence >= MAX_EVENTS_PER_RUN - 1:
                # Keep the failed-attempt ledger while using the reserved terminal slot.
                row = conn.execute(select(runs).where(runs.c.run_id == run_id)).mappings().one()
                self.end_event_limit(conn, row)
                return
            payload = {
                "tool": call["tool"],
                "status": "ok" if status < 400 else "error",
                "tool_call_id": call["tool_call_id"],
                "duration_ms": duration,
                "replayed": replayed,
            }
            payload |= {k: v for k, v in (("code", code), ("artifact_id", artifact_id)) if v}
            self.event(conn, run_id, "tool", payload)

    def lease_run(self, conn, actor, lease, run_id=None):
        # Somente o titular da reserva registra tentativas no run, inclusive após o término.
        if actor["role"] != "worker" or not lease:
            return None
        statement = select(runs).where(
            runs.c.lease_sha256 == token_hash(lease), runs.c.worker_id == actor["principal_id"]
        )
        if run_id is not None:
            statement = statement.where(runs.c.run_id == str(run_id))
        row = conn.execute(statement.with_for_update()).mappings().first()
        return dict(row) if row else None

    def tool_call_history(self, conn, run_id):
        """Compatibility stage ledger; use tracking.history for physical request counts."""
        return [
            dict(r)
            for r in conn.execute(
                select(tool_calls)
                .where(tool_calls.c.run_id == str(run_id))
                .order_by(tool_calls.c.started_at, tool_calls.c.tool_call_id, tool_calls.c.attempt)
            ).mappings()
        ]

    def write_artifact(self, actor, query, lease, tool, call):
        raw = query.model_dump(mode="json")
        hashed = digest(raw)
        with self.transaction() as conn:
            row = self.tool_context(conn, actor, query, lease, call, write=True)
            self.validate_sources(conn, row["context"], query.evidence)
            if tool == "registrar_pendencia":
                requirement = conn.execute(
                    select(requirements.c.payload).where(
                        requirements.c.process_id == query.process_id,
                        requirements.c.corpus_version == query.corpus_version,
                        requirements.c.requirements_version == query.requirements_version,
                        requirements.c.requirement_id == query.requirement_id,
                    )
                ).first()
                if requirement is None:
                    fail(422, "validation_error", "Requisito não pertence ao checklist versionado.")
                try:
                    item = Requirement.model_validate(requirement[0])
                    if item.requirement_id != query.requirement_id:
                        raise ValueError("Requirement payload differs from stored identity")
                except (ValidationError, ValueError):
                    fail(
                        500, "invalid_response", "Requisito armazenado inconsistente.", query.run_id
                    )
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
                receipt = self.artifact_receipt(prior, tool, query, same_input=False)
                if prior["input_sha256"] != hashed or prior["payload"] != raw:
                    fail(409, "idempotency_conflict", "Chave reutilizada com outro conteúdo.")
                self.tool_attempt(
                    conn,
                    str(query.run_id),
                    call,
                    200,
                    replayed=True,
                    artifact_id=prior["artifact_id"],
                )
                return {**receipt, "replayed": True}
            artifact_id = str(uuid4())
            receipt = {
                **row["context"],
                "artifact_id": artifact_id,
                "persisted_at": datetime.now(UTC).isoformat(),
                "content_sha256": hashlib.sha256(query.content.encode()).hexdigest(),
                "replayed": False,
            }
            stored = dict(
                artifact_id=artifact_id,
                run_id=str(query.run_id),
                tool=tool,
                idempotency_key=query.idempotency_key,
                input_sha256=hashed,
                payload=raw,
                receipt=receipt,
            )
            self.artifact_receipt(stored, tool, query)
            conn.execute(insert(artifacts).values(**stored))
            persisted = (
                conn.execute(select(artifacts).where(artifacts.c.artifact_id == artifact_id))
                .mappings()
                .first()
            )
            self.artifact_receipt(persisted, tool, query)
            self.tool_attempt(conn, str(query.run_id), call, 200, artifact_id=artifact_id)
        # Leitura independente da transação que confirmou a gravação.
        with self.engine.connect() as conn:
            persisted = (
                conn.execute(select(artifacts).where(artifacts.c.artifact_id == artifact_id))
                .mappings()
                .first()
            )
            return self.artifact_receipt(persisted, tool, query)

    def artifact_receipt(self, stored, tool, query, *, same_input=True):
        """Conferência comum de efeito/recibo antes de confirmar ou reproduzir escrita."""
        validated = validate_artifact(stored, expected_tool=tool, expected_context=query)
        if same_input and validated.payload.model_dump(mode="json") != query.model_dump(
            mode="json"
        ):
            fail(
                500,
                "invalid_response",
                "Artefato ou recibo armazenado inconsistente.",
                query.run_id,
            )
        return validated.receipt.model_dump(mode="json")

    def get_artifact(self, actor, artifact_id) -> ArtifactResponse:
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(artifacts).where(artifacts.c.artifact_id == artifact_id))
                .mappings()
                .first()
            )
            if row is None:
                fail(404, "not_found", "Artefato não encontrado.")
            try:
                owner_run = self.owned_run(conn, actor, row["run_id"])
                context = ToolContext.model_validate(owner_run["context"])
                if (
                    str(context.run_id) != owner_run["run_id"]
                    or context.model_dump(mode="json") != owner_run["context"]
                ):
                    raise ValueError("Stored run context is inconsistent")
            except (ValidationError, ValueError, KeyError, TypeError):
                fail(500, "invalid_response", "Contexto armazenado inconsistente.")
            return validate_artifact(row, expected_tool=row["tool"], expected_context=context)

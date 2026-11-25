"""Registro experimental com revisões, portado do task/langgraph-grafo (856ff06, João Enomoto).

Mantém as regras do original (``save_experiment_run``/``update_experiment_run``): primeira
revisão 1, reenvio idêntico idempotente, revisões sequenciais e sem alterar identidade,
protocolo, orçamento, métricas já registradas nem avaliação externa. A v0.2 acrescenta:
escrita só pelo worker com a reserva do run de benchmark, contexto igual ao da reserva e
``tool_calls`` iguais ao histórico do servidor. O servidor valida; nunca reescreve o registro.
"""

import time

from sqlalchemy import insert, select, update

from contracts.execution import TERMINAL_STATUSES
from contracts.models import (
    FIRST_REVISION,
    UNOBSERVED_PARAMETER,
    ExperimentRun,
    experiment_record,
)
from services.backend.auth import authorize
from services.backend.errors import ToolFailure, fail
from services.backend.result_integrity import validate_experiment_history
from services.backend.schema import experiment_run_revisions, experiment_runs, runs

TERMINAL = TERMINAL_STATUSES
STABLE_FIELDS = (
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
# UNOBSERVED_PARAMETER (P10): o servidor não consegue confirmar a contagem; só exige inteiro
# não negativo e não decrescente entre revisões.
STABLE_PARAMETERS = (
    "level",
    "max_model_calls",
    "max_tool_calls",
    "timeout_seconds",
    "model_timeout_seconds",
    "backend_timeout_seconds",
)


def canonical(run: ExperimentRun | dict) -> dict:
    """Forma JSON comparável, igual para o corpo recebido e para o payload persistido."""
    if isinstance(run, dict):
        run = ExperimentRun.model_validate(run)
    # Sem "revision", o servidor grava a revisão 1; regra única em contracts.models.
    return experiment_record(run)


def revision_of(run: ExperimentRun) -> int:
    value = run.parameters.get("revision", FIRST_REVISION)
    if not isinstance(value, int) or isinstance(value, bool):
        fail(409, "idempotency_conflict", "Revisão experimental deve ser um inteiro.", run.run_id)
    return value


def check_scope(row, report: ExperimentRun) -> None:
    """Registro pertence ao run reservado e não traz avaliação externa (mesma regra do result)."""
    if (
        report.model_dump(mode="json", include=set(row["context"])) != row["context"]
        or report.executor != row["executor"]
        or report.verified_success is not None
        or report.evaluator is not None
        or any(getattr(report, k) != v for k, v in row["task_metadata"].items())
    ):
        fail(422, "validation_error", "Registro experimental incompatível.")
    unobserved = report.parameters.get(UNOBSERVED_PARAMETER, 0)
    if not isinstance(unobserved, int) or isinstance(unobserved, bool) or unobserved < 0:
        fail(422, "validation_error", "unobserved_tool_calls deve ser inteiro não negativo.")


def check_revision(previous: ExperimentRun, run: ExperimentRun) -> None:
    """Regras de revisão do original; falha vira 409 como em ``PUT /experiments``."""

    def conflict(message):
        fail(409, "idempotency_conflict", message, run.run_id)

    if any(getattr(previous, field) != getattr(run, field) for field in STABLE_FIELDS):
        conflict("A revisão altera a identidade da execução.")
    if any(previous.parameters.get(k) != run.parameters.get(k) for k in STABLE_PARAMETERS):
        conflict("A revisão altera o protocolo ou orçamento da execução.")
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
        or (
            UNOBSERVED_PARAMETER in previous.parameters
            and run.parameters.get(UNOBSERVED_PARAMETER, -1)
            < previous.parameters[UNOBSERVED_PARAMETER]
        )
    ):
        conflict("A revisão reduz métricas ou altera avaliação externa.")
    if revision_of(run) != revision_of(previous) + 1:
        conflict("A revisão experimental não é sequencial.")


class ExperimentRecords:
    """Operações de ``/experiments`` sobre as transações e reservas do ExecutionService."""

    def __init__(self, service):
        self.service = service

    def _current(self, conn, run_id):
        return (
            conn.execute(select(experiment_runs).where(experiment_runs.c.run_id == str(run_id)))
            .mappings()
            .first()
        )

    def _writable(self, conn, actor, lease, run: ExperimentRun):
        row = self.service.worker_run(conn, actor, run.run_id, lease, terminal=True)
        if row["kind"] != "benchmark":
            fail(
                422, "validation_error", "Registro experimental só existe em benchmark.", run.run_id
            )
        check_scope(row, run)
        return row

    def _store(self, conn, run: ExperimentRun, revision: int, payload: dict, *, first: bool):
        now = time.time()
        values = dict(revision=revision, payload=payload, updated_at=now)
        if first:
            conn.execute(insert(experiment_runs).values(run_id=str(run.run_id), **values))
        else:
            conn.execute(
                update(experiment_runs)
                .where(experiment_runs.c.run_id == str(run.run_id))
                .values(**values)
            )
        conn.execute(
            insert(experiment_run_revisions).values(
                run_id=str(run.run_id), revision=revision, payload=payload, recorded_at=now
            )
        )

    def save(self, actor, lease, run: ExperimentRun) -> ExperimentRun:
        if revision_of(run) != 1:
            fail(
                409,
                "idempotency_conflict",
                "A primeira revisão de ExperimentRun deve ser 1.",
                run.run_id,
            )
        payload = canonical(run)
        with self.service.transaction() as conn:
            row = self._writable(conn, actor, lease, run)
            current = self._current(conn, run.run_id)
            if current is not None:
                if canonical(current["payload"]) != payload:
                    fail(
                        409,
                        "idempotency_conflict",
                        "run_id já registrado com conteúdo diferente.",
                        run.run_id,
                    )
                return ExperimentRun.model_validate(current["payload"])
            if row["status"] in TERMINAL:
                fail(409, "conflict", "Execução não está ativa.", run.run_id)
            validate_experiment_history(conn, row, run)
            self._store(conn, run, 1, payload, first=True)
        return ExperimentRun.model_validate(payload)

    def update(self, actor, lease, run_id, run: ExperimentRun) -> ExperimentRun:
        if str(run.run_id) != str(run_id):
            fail(
                422, "validation_error", "run_id do caminho e do registro devem ser iguais.", run_id
            )
        payload = canonical(run)
        with self.service.transaction() as conn:
            row = self._writable(conn, actor, lease, run)
            current = self._current(conn, run.run_id)
            if current is None:
                fail(409, "idempotency_conflict", "Execução ainda não foi registrada.", run_id)
            if canonical(current["payload"]) == payload:
                return ExperimentRun.model_validate(current["payload"])
            if row["status"] in TERMINAL:
                fail(409, "conflict", "Execução não está ativa.", run_id)
            check_revision(ExperimentRun.model_validate(current["payload"]), run)
            validate_experiment_history(conn, row, run)
            self._store(conn, run, revision_of(run), payload, first=False)
        return ExperimentRun.model_validate(payload)

    def _readable(self, conn, actor, run_id):
        if actor["role"] == "operator":
            return self.service.owned_run(conn, actor, run_id)
        row = conn.execute(select(runs).where(runs.c.run_id == str(run_id))).mappings().first()
        if row is None or actor["role"] != "worker" or actor.get("executor") != row["executor"]:
            fail(404, "not_found", "Execução experimental não encontrada.", run_id)
        try:
            authorize(
                conn,
                actor["principal_id"],
                row["context"]["process_id"],
                row["context"]["corpus_version"],
            )
        except ToolFailure:
            # Sem concessão, o run não existe para este worker: 404, sem confirmar o run_id.
            fail(404, "not_found", "Execução experimental não encontrada.", run_id)
        return dict(row)

    def get(self, actor, run_id) -> ExperimentRun:
        with self.service.engine.connect() as conn:
            self._readable(conn, actor, run_id)
            current = self._current(conn, run_id)
        if current is None:
            fail(404, "not_found", "Execução experimental não encontrada.", run_id)
        return ExperimentRun.model_validate(current["payload"])

    def revisions(self, actor, run_id) -> list[ExperimentRun]:
        with self.service.engine.connect() as conn:
            self._readable(conn, actor, run_id)
            rows = conn.execute(
                select(experiment_run_revisions.c.payload)
                .where(experiment_run_revisions.c.run_id == str(run_id))
                .order_by(experiment_run_revisions.c.revision)
            ).scalars()
            return [ExperimentRun.model_validate(payload) for payload in rows]

    @staticmethod
    def latest(conn, run_id) -> dict | None:
        """Payload da última revisão, para conferir o resultado final do run."""
        return conn.execute(
            select(experiment_runs.c.payload).where(experiment_runs.c.run_id == str(run_id))
        ).scalar_one_or_none()

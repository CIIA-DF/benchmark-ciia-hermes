"""Ponte v0.1 → v0.2: expõe um adaptador síncrono run() como AgentAdapter.stream.

Hermes, LangGraph e o runner da Evaluation implementam ``run(task, context) -> ExperimentRun``
com um cliente de tools síncrono. O worker v0.2 espera ``stream(ClaimedRun, AsyncToolClient)``.
A ponte executa o ``run()`` numa thread e entrega a ele um cliente síncrono que delega ao
``AsyncToolClient`` do worker: token da reserva, ``X-Tool-Call-Id``, retries e tradução de
erros são os mesmos para os dois executores.

O ``ExperimentSink`` implementa o ``ExperimentRunSink`` do LangGraph (task/langgraph-grafo,
856ff06, João Enomoto) sobre as rotas ``/experiments`` portadas para a v0.2, com o token e a
reserva do worker. Antes de gravar, ``tool_calls`` e ``persisted_artifact_ids`` passam a ser os
do cliente comum, porque o servidor confere o registro com o próprio histórico.

Limites assumidos: não há eventos parciais (o texto sai inteiro ao final) e uma thread em
execução não pode ser interrompida; o prazo continua sendo imposto pela reserva do servidor.
"""

import asyncio
import inspect
from collections.abc import AsyncIterator, Callable
from typing import Protocol
from uuid import UUID, uuid4

import httpx

from agents.interface import AsyncToolClient
from contracts.execution import AgentEvent, AgentResult, ClaimedRun
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext, experiment_record

# Tamanho máximo de AgentEvent.text no contrato v0.2.
DELTA_CHARS = 4000
# Campos que identificam a execução e não podem divergir do que o servidor reservou.
SCOPE_FIELDS = ("run_id", "process_id", "corpus_version", "requirements_version")
TASK_FIELDS = ("task_id", "split", "repetition")


class RunAdapter(Protocol):
    def run(self, task: str, context: ToolContext) -> ExperimentRun: ...


class SyncToolClient:
    """Cliente síncrono para código run(); cada chamada roda no laço do worker."""

    def __init__(self, tools: AsyncToolClient, loop: asyncio.AbstractEventLoop):
        self._tools = tools
        self._loop = loop
        # Falhas definitivas das tools; distinguem timeout de tool de timeout do modelo.
        self.errors: list[BaseException] = []

    @property
    def calls(self) -> list[ToolCallRecord]:
        return self._tools.calls

    def call(self, name: str, arguments: dict) -> dict:
        # Corrigível → dict com "error"; definitivo → ToolCallError, como no cliente comum.
        future = asyncio.run_coroutine_threadsafe(self._tools.call(name, arguments), self._loop)
        try:
            return future.result()
        except Exception as exc:
            self.errors.append(exc)
            raise

    def close(self):
        """Compatível com ToolClient.close(); a conexão pertence ao worker."""


def normalized(report: ExperimentRun, calls: list[ToolCallRecord]) -> ExperimentRun:
    """Registro com as chamadas e artefatos do cliente comum, iguais para os dois executores."""
    artifacts = list(dict.fromkeys(c.artifact_id for c in calls if c.artifact_id is not None))
    return report.model_copy(
        update={"tool_calls": list(calls), "persisted_artifact_ids": artifacts}
    )


class ExperimentSink:
    """``save``/``get``/``update`` do LangGraph sobre ``/experiments`` da v0.2.

    Em runs de chat não há registro no servidor: o sink guarda a última revisão só em memória.
    """

    def __init__(self, tools: AsyncToolClient, loop: asyncio.AbstractEventLoop):
        self._tools = tools
        self._loop = loop
        self.latest: ExperimentRun | None = None
        # Falhas de /experiments são do backend, não do modelo (ver _failure).
        self.errors: list[BaseException] = []

    def _run(self, coroutine):
        try:
            return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result()
        except Exception as exc:
            self.errors.append(exc)
            raise

    async def _send(self, method: str, path: str, run: ExperimentRun) -> ExperimentRun:
        headers = {"X-Run-Token": self._tools.execution.run_token}
        response = await self._tools.client.request(
            method, path, json=run.model_dump(mode="json"), headers=headers
        )
        response.raise_for_status()
        return ExperimentRun.model_validate(response.json())

    def _write(self, method: str, path: str, run: ExperimentRun) -> ExperimentRun:
        run = normalized(run, self._tools.calls)
        if self._tools.execution.kind == "benchmark":
            run = self._run(self._send(method, path, run))
        self.latest = run
        return run

    def save(self, run: ExperimentRun) -> ExperimentRun:
        return self._write("POST", "/experiments", run)

    def update(self, run: ExperimentRun) -> ExperimentRun:
        return self._write("PUT", f"/experiments/{run.run_id}", run)

    def get(self, run_id: UUID) -> ExperimentRun | None:
        if self._tools.execution.kind != "benchmark":
            return self.latest if self.latest and self.latest.run_id == run_id else None

        async def read():
            response = await self._tools.client.get(f"/experiments/{run_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return ExperimentRun.model_validate(response.json())

        return self._run(read())


def task_fields(execution: ClaimedRun) -> dict:
    """Campos de RunMetadata vindos da reserva; os de versão ficam com a equipe."""
    return dict(execution.task_metadata)


AdapterFactory = (
    Callable[[SyncToolClient, ClaimedRun], RunAdapter]
    | Callable[[SyncToolClient, ExperimentSink, ClaimedRun], RunAdapter]
)


def _build(factory, client: SyncToolClient, sink: ExperimentSink, execution: ClaimedRun):
    # Fábricas de três argumentos recebem o sink; as de dois continuam aceitas.
    try:
        arity = len(inspect.signature(factory).parameters)
    except (TypeError, ValueError):
        arity = 2
    return factory(client, sink, execution) if arity >= 3 else factory(client, execution)


def _invoke(adapter: RunAdapter, task: str, context: ToolContext):
    # LangGraph expõe run_with_result (resposta + registro); Hermes guarda final_response.
    if callable(getattr(adapter, "run_with_result", None)):
        result = adapter.run_with_result(task, context)
        return result.experiment_run, result.response
    report = adapter.run(task, context)
    return report, getattr(adapter, "final_response", "") or ""


def _failure(exc: BaseException, client: SyncToolClient, sink: ExperimentSink) -> str:
    # Só timeout HTTP fora das tools e do sink (o modelo) vira model_timeout; o resto é do
    # adaptador.
    backend = [*client.errors, *sink.errors]
    from_backend = any(exc is e or exc.__cause__ is e or exc.__context__ is e for e in backend)
    if isinstance(exc, httpx.TimeoutException) and not from_backend:
        return "model_timeout"
    return "adapter_error"


def _checked(report, execution: ClaimedRun, calls: list[ToolCallRecord]) -> ExperimentRun:
    if not isinstance(report, ExperimentRun):
        raise TypeError("run() deve retornar ExperimentRun.")
    expected = {**execution.context, **execution.task_metadata, "executor": execution.executor}
    produced = report.model_dump(mode="json")
    for key, value in expected.items():
        if produced.get(key) != (str(value) if key == "run_id" else value):
            raise ValueError(f"ExperimentRun.{key} difere da execução reservada.")
    # Paridade: o registro declarado vem do cliente comum, não do rastreio próprio do adaptador.
    return normalized(report, calls)


class RunBridge:
    """AgentAdapter.stream sobre uma fábrica que cria o adaptador run() por execução."""

    def __init__(self, factory: AdapterFactory):
        self.factory = factory

    async def stream(
        self, execution: ClaimedRun, tools: AsyncToolClient
    ) -> AsyncIterator[AgentEvent | AgentResult]:
        yield AgentEvent(
            event_id=uuid4(), kind="status", text="Executando adaptador síncrono (ponte v0.1)"
        )
        loop = asyncio.get_running_loop()
        client = SyncToolClient(tools, loop)
        sink = ExperimentSink(tools, loop)
        context = ToolContext.model_validate(execution.context)
        try:
            # Construção e execução fora do laço: o heartbeat da reserva continua ativo.
            report, answer = await asyncio.to_thread(
                lambda: _invoke(
                    _build(self.factory, client, sink, execution), execution.task, context
                )
            )
            experiment = None
            if execution.kind == "benchmark":
                experiment = _checked(report, execution, tools.calls)
                if sink.latest is not None:
                    # O servidor exige no resultado a última revisão gravada em /experiments.
                    if normalized(sink.latest, tools.calls) != sink.latest:
                        raise ValueError("Houve chamadas de tool depois da última revisão.")
                    # A ponte não grava revisões pelo adaptador (ADR 011): um relatório final
                    # diferente do último gravado seria perdido em silêncio.
                    if experiment_record(experiment) != experiment_record(sink.latest):
                        raise ValueError(
                            "Relatório final difere da última revisão gravada; "
                            "grave a revisão final pelo sink."
                        )
                    experiment = sink.latest
        except Exception as exc:  # noqa: BLE001 - a falha vira resultado terminal do contrato
            yield AgentResult(status="failed", error_code=_failure(exc, client, sink))
            return
        if not isinstance(answer, str):
            answer = ""
        for offset in range(0, len(answer), DELTA_CHARS):
            yield AgentEvent(
                event_id=uuid4(), kind="text_delta", text=answer[offset : offset + DELTA_CHARS]
            )
        yield AgentResult(status="succeeded", answer=answer, experiment=experiment)

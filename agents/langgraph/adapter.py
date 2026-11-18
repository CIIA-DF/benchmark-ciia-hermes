"""Adaptador LangGraph com limites, medição e persistência via backend."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from time import perf_counter
from typing import Literal, Protocol
from uuid import UUID, uuid4

from langchain_core.messages import AIMessage

from agents.interface import AgentAdapter, ModelConfig
from agents.langgraph.graph import (
    DEFAULT_LIMITS,
    DEFAULT_SYSTEM_PROMPT,
    ExecutionLevel,
    ExecutionLimits,
    ToolClientLike,
    build_graph,
    checkpoint_config,
    follow_up_state,
    initial_state,
)
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext


@dataclass(frozen=True)
class RunMetadata:
    task_id: str
    split: Literal["development", "final"]
    repetition: int
    code_commit: str
    harness_version: str
    adapter_version: str
    endpoint_id: str


@dataclass(frozen=True)
class AgentResult:
    response: str
    experiment_run: ExperimentRun


class ExperimentRunSink(Protocol):
    def save(self, run: ExperimentRun) -> ExperimentRun: ...

    def get(self, run_id: UUID) -> ExperimentRun | None: ...

    def update(self, run: ExperimentRun) -> ExperimentRun: ...


class RecordingToolClient:
    """Registra metadados de chamadas sem guardar entradas ou conteúdo retornado."""

    def __init__(self, client: ToolClientLike):
        self.client = client
        self.records: list[dict] = []
        self.lock = Lock()

    def call(self, name: str, arguments: dict) -> dict:
        started = perf_counter()
        status = "ok"
        try:
            return self.client.call(name, arguments)
        except Exception:
            status = "error"
            raise
        finally:
            record = {
                "tool_call_id": f"tool-{uuid4().hex}",
                "tool": name,
                "duration_ms": max(0, (perf_counter() - started) * 1000),
                "status": status,
                "artifact_id": None,
            }
            with self.lock:
                self.records.append(record)


def _message_text(message: AIMessage | None) -> str:
    if message is None:
        return ""
    content = message.content
    if isinstance(content, str):
        return content
    return "\n".join(
        str(part.get("text", "")) for part in content if isinstance(part, dict)
    ).strip()


class LangGraphAdapter(AgentAdapter):
    """Executor de uma tarefa; receba modelo e armazenamento já configurados.

    O modelo concreto é injetado pelo chamador porque o provedor e seu protocolo
    de tool calling ainda precisam de confirmação no projeto.
    """

    def __init__(
        self,
        *,
        model,
        model_config: ModelConfig,
        tool_client: ToolClientLike,
        metadata: RunMetadata,
        sink: ExperimentRunSink,
        level: ExecutionLevel = "chained",
        limits: ExecutionLimits | None = None,
        checkpointer=None,
        system_prompt: str | None = None,
    ):
        if level == "resumable" and checkpointer is None:
            raise ValueError("O nível resumable requer um checkpointer persistente.")
        self.model = model
        self.model_config = model_config
        self.tool_client = RecordingToolClient(tool_client)
        self.metadata = metadata
        self.sink = sink
        self.level = level
        self.limits = limits
        self.checkpointer = checkpointer
        self.system_prompt = system_prompt

    @classmethod
    def from_environment(
        cls,
        *,
        model_factory: Callable[[ModelConfig], object],
        tool_client: ToolClientLike,
        metadata: RunMetadata,
        sink: ExperimentRunSink,
        **options,
    ):
        """Cria o chat model via fábrica específica do provedor configurado."""

        config = ModelConfig.from_environment()
        return cls(
            model=model_factory(config),
            model_config=config,
            tool_client=tool_client,
            metadata=metadata,
            sink=sink,
            **options,
        )

    def _execute(self, task: str, context: ToolContext, *, resume: bool) -> AgentResult:
        started_at = datetime.now(UTC)
        started = perf_counter()
        tool_offset = len(self.tool_client.records)
        previous_run = self.sink.get(context.run_id) if resume else None
        if resume and previous_run is None:
            raise ValueError("Não há ExperimentRun persistido para continuar.")
        limits = self.limits or DEFAULT_LIMITS[self.level]
        graph_kwargs = {
            "level": self.level,
            "limits": limits,
            "checkpointer": self.checkpointer,
        }
        if self.system_prompt is not None:
            graph_kwargs["system_prompt"] = self.system_prompt
        graph = build_graph(self.model, self.tool_client, context, **graph_kwargs)
        config = checkpoint_config(context) if self.level == "resumable" else None
        initial = (
            follow_up_state(task)
            if resume
            else initial_state(task, level=self.level, limits=limits)
        )
        state = None
        failure_category = None
        try:
            state = graph.invoke(initial, config=config) if config else graph.invoke(initial)
        except Exception as exc:
            failure_category = type(exc).__name__
        measured_ms = max(0, (perf_counter() - started) * 1000)
        messages = state.get("messages", []) if state else []
        final_message = messages[-1] if messages and isinstance(messages[-1], AIMessage) else None
        response = _message_text(final_message)
        status = state.get("status", "error") if state else "error"
        if failure_category:
            status = "error"
        records = (
            state.get("tool_call_records", [])
            if state
            else previous_run.tool_calls
            if previous_run
            else self.tool_client.records[tool_offset:]
        )
        call_records = [ToolCallRecord.model_validate(record) for record in records]
        revision = int(previous_run.parameters.get("revision", 1)) + 1 if previous_run else 1
        parameters: dict[str, str | float | int | bool] = {
            "level": self.level,
            "max_model_calls": limits.max_model_calls,
            "max_tool_calls": min(limits.max_tool_calls, 1)
            if self.level == "assisted"
            else limits.max_tool_calls,
            "timeout_seconds": limits.timeout_seconds,
            "model_timeout_seconds": self.model_config.timeout_seconds,
            "status": status,
            "revision": revision,
        }
        if failure_category:
            parameters["failure_category"] = failure_category
        backend_timeout = getattr(self.tool_client.client, "timeout_seconds", None)
        if backend_timeout is not None:
            parameters["backend_timeout_seconds"] = backend_timeout
        run = ExperimentRun(
            **context.model_dump(),
            task_id=self.metadata.task_id,
            split=self.metadata.split,
            executor="langgraph",
            repetition=self.metadata.repetition,
            code_commit=self.metadata.code_commit,
            harness_version=self.metadata.harness_version,
            adapter_version=self.metadata.adapter_version,
            model=self.model_config.model,
            endpoint_id=self.metadata.endpoint_id,
            prompt_sha256=sha256(
                (self.system_prompt or DEFAULT_SYSTEM_PROMPT).encode()
            ).hexdigest(),
            parameters=parameters,
            started_at=(
                datetime.fromisoformat(state["started_at"])
                if state and state.get("started_at")
                else previous_run.started_at
                if previous_run
                else started_at
            ),
            latency_ms=(
                state.get("elapsed_ms", 0)
                if state
                else previous_run.latency_ms + measured_ms
                if previous_run
                else measured_ms
            ),
            tool_calls=call_records,
            input_tokens=(
                state["input_tokens"]
                if state and state.get("input_tokens")
                else previous_run.input_tokens
                if previous_run
                else None
            ),
            output_tokens=(
                state["output_tokens"]
                if state and state.get("output_tokens")
                else previous_run.output_tokens
                if previous_run
                else None
            ),
            agent_declared_success=status == "completed" and bool(response.strip()),
            persisted_artifact_ids=[],
            verified_success=None,
            evaluator=None,
        )
        persisted = self.sink.update(run) if resume else self.sink.save(run)
        return AgentResult(response=response, experiment_run=persisted)

    def run(self, task: str, context: ToolContext) -> ExperimentRun:
        """Executa e persiste o registro; sucesso verificado fica com o avaliador."""

        return self._execute(task, context, resume=False).experiment_run

    def run_with_result(self, task: str, context: ToolContext) -> AgentResult:
        """Retorna a resposta para o harness sem persistir seu conteúdo no banco."""

        return self._execute(task, context, resume=False)

    def continue_run(self, task: str, context: ToolContext) -> AgentResult:
        """Continua o mesmo thread/run_id com o checkpoint existente."""

        if self.level != "resumable":
            raise ValueError("Somente o nível resumable aceita continuação.")
        return self._execute(task, context, resume=True)

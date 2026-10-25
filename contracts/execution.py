"""Contratos v0.2 de conversa, execução e streaming para ambos os adaptadores."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from contracts.models import Contract, Evidence, ExperimentRun, Identifier, InventoryEvidence, Text

Executor = Literal["simulation", "hermes", "langgraph"]
RunStatus = Literal["queued", "running", "succeeded", "failed", "timed_out"]
Reference = Evidence | InventoryEvidence


class ExecutionScope(Contract):
    process_id: Identifier
    corpus_version: Identifier
    requirements_version: Identifier
    executor: Executor = "simulation"


class ConversationInput(ExecutionScope):
    participant_id: UUID | None = None


class MessageInput(Contract):
    content: Text
    idempotency_key: Identifier


class RunInput(ExecutionScope):
    task: Text
    idempotency_key: Identifier
    task_id: Identifier
    split: Literal["development", "final"] = "development"
    repetition: int = Field(default=1, ge=1)


class ClaimInput(Contract):
    executor: Executor
    run_id: UUID | None = None


class AgentEvent(Contract):
    event_id: UUID
    kind: Literal["status", "text_delta"]
    # Deltas must preserve spaces and line breaks, unlike general contract strings.
    text: str = Field(min_length=1, max_length=4000, strict=True)

    model_config = {"extra": "forbid", "str_strip_whitespace": False}


class AgentResult(Contract):
    model_config = {"extra": "forbid", "str_strip_whitespace": False}
    status: Literal["succeeded", "failed", "timed_out"]
    answer: str = Field(default="", max_length=100_000)
    sources: list[Reference] = Field(default_factory=list, max_length=100)
    error_code: Literal["adapter_error", "context_limit", "model_timeout"] | None = None
    experiment: ExperimentRun | None = None


class ClaimedRun(Contract):
    run_id: UUID
    context: dict[str, str]
    history: list[dict[str, str]]
    task: Text
    task_metadata: dict[str, str | int]
    kind: Literal["chat", "benchmark"]
    executor: Executor
    run_token: str = Field(repr=False)
    lease_seconds: int = Field(gt=0)
    heartbeat_seconds: int = Field(gt=0)


class StoredResult(AgentResult):
    error_code: (
        Literal["adapter_error", "context_limit", "model_timeout", "worker_timeout"] | None
    ) = None


class ArtifactSummary(Contract):
    artifact_id: UUID
    tool: Literal["registrar_pendencia", "salvar_minuta"]


class RunResponse(Contract):
    model_config = {"extra": "forbid", "str_strip_whitespace": False}
    run_id: UUID
    conversation_id: UUID | None
    kind: Literal["chat", "benchmark"]
    executor: Executor
    status: RunStatus
    context: dict[str, str]
    created_at: float
    started_at: float | None
    finished_at: float | None
    result: StoredResult | None
    partial_answer: str
    last_event_id: int = Field(ge=0)
    artifacts: list[ArtifactSummary] = Field(default_factory=list)


class ConversationResponse(ConversationInput):
    conversation_id: UUID
    owner_id: str
    created_at: float


class MessageResponse(Contract):
    model_config = {"extra": "forbid", "str_strip_whitespace": False}
    message_id: UUID
    conversation_id: UUID
    run_id: UUID
    role: Literal["user", "assistant"]
    content: str
    created_at: float


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse]
    runs: list[RunResponse]


class ExecutorCapability(Contract):
    name: Executor
    available: bool
    simulation: bool


class CapabilitiesResponse(Contract):
    executors: list[ExecutorCapability]
    can_write: bool
    profile: str


class HeartbeatResponse(Contract):
    status: Literal["running"]


class EventReceipt(Contract):
    sequence: int = Field(gt=0)

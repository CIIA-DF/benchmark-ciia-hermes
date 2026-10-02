"""Contratos v0.1: modelos compartilhados; mudanças exigem revisão das equipes."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")]
Text = Annotated[str, Field(min_length=1, max_length=100_000)]
Completeness = Literal["complete", "partial", "unknown"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Process(Contract):
    process_id: Identifier
    title: Text
    corpus_version: Identifier
    requirements_version: Identifier
    export_completeness: Completeness
    export_note: Text


class Page(Contract):
    number: int = Field(ge=1)
    text: Text


class Document(Contract):
    document_id: Identifier
    process_id: Identifier
    corpus_version: Identifier
    title: Text
    source: Text
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pages: list[Page] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_pages(self):
        if len({page.number for page in self.pages}) != len(self.pages):
            raise ValueError("Números de página devem ser únicos.")
        return self


class Chunk(Contract):
    chunk_id: Identifier
    process_id: Identifier
    document_id: Identifier
    corpus_version: Identifier
    source: Text
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: Text

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("Offsets devem delimitar exatamente o texto do chunk.")
        return self


class ToolContext(Contract):
    run_id: UUID
    process_id: Identifier
    corpus_version: Identifier
    requirements_version: Identifier


class ProcessResult(ToolContext):
    process: Process


class SearchInput(ToolContext):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=5, ge=1, le=20)


class SearchResult(ToolContext):
    export_completeness: Completeness
    items: list[Chunk]
    warning: str = "Não localizar um documento não prova ausência no processo original."


class ReadInput(ToolContext):
    document_id: Identifier


class DocumentResult(ToolContext):
    document: Document


class ToolError(Contract):
    code: Literal[
        "validation_error",
        "not_found",
        "version_mismatch",
        "not_implemented",
        "storage_unavailable",
        "idempotency_conflict",
        "unauthorized",
    ]
    message: str
    run_id: UUID | None = None
    retryable: bool = False


class Requirement(Contract):
    requirement_id: Identifier
    description: Text
    source: Text


class RequirementsResult(ToolContext):
    items: list[Requirement]


class Evidence(Contract):
    document_id: Identifier
    chunk_id: Identifier
    page: int = Field(ge=1)


class WriteInput(ToolContext):
    idempotency_key: Identifier
    content: Text
    evidence: list[Evidence]
    evidence_note: Text


class WriteReceipt(ToolContext):
    artifact_id: Identifier
    persisted_at: datetime
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    replayed: bool


class ToolCallRecord(Contract):
    tool_call_id: Identifier
    tool: Identifier
    duration_ms: float = Field(ge=0)
    status: Literal["ok", "error"]
    artifact_id: Identifier | None = None


class ExperimentRun(ToolContext):
    contract_version: Literal["0.1"] = "0.1"
    task_id: Identifier
    split: Literal["development", "final"]
    executor: Literal["hermes", "langgraph", "simulation"]
    repetition: int = Field(ge=1)
    code_commit: Text
    harness_version: Text
    adapter_version: Text
    model: Text
    endpoint_id: Identifier
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: dict[str, str | float | int | bool]
    started_at: datetime
    latency_ms: float = Field(ge=0)
    tool_calls: list[ToolCallRecord]
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    agent_declared_success: bool
    persisted_artifact_ids: list[Identifier]
    verified_success: bool | None
    evaluator: str | None

"""Contratos compartilhados de ferramentas; versão de aplicação 0.3."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")]
# U+0000 é recusado como em SearchInput.query (F2): o PostgreSQL não o armazena em texto (P3).
Text = Annotated[str, Field(min_length=1, max_length=100_000, pattern=r"^[^\x00]+$")]
# Mesma recusa para textos que podem ser vazios e sem limite próprio (P7).
NulFree = Annotated[str, Field(pattern=r"^[^\x00]*$")]
ParameterName = Annotated[str, Field(min_length=1, max_length=120, pattern=r"^[^\x00]+$")]
Completeness = Literal["complete", "partial", "unknown"]
ToolName = Literal[
    "consultar_processo",
    "buscar_documentos",
    "ler_documento",
    "consultar_requisitos",
    "registrar_pendencia",
    "salvar_minuta",
]
ErrorCode = Literal[
    "validation_error",
    "not_found",
    "version_mismatch",
    "not_implemented",
    "storage_unavailable",
    "idempotency_conflict",
    "unauthorized",
    "forbidden",
    "conflict",
    "context_limit",
    "executor_unavailable",
    "budget_exceeded",
    "invalid_response",
    "internal_error",
    "http_error",
    "method_not_allowed",
    "payload_too_large",
    "resource_limit",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class Process(Contract):
    process_id: Identifier
    title: Text
    corpus_version: Identifier
    requirements_version: Identifier
    export_completeness: Completeness
    export_note: Text


class Page(Contract):
    number: StrictInt = Field(ge=1)
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
    page: StrictInt = Field(ge=1)
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    text: Text

    @model_validator(mode="after")
    def valid_offsets(self):
        if self.end <= self.start or self.end - self.start != len(self.text):
            raise ValueError("Offsets devem delimitar exatamente o texto do chunk.")
        return self


class ToolContext(Contract):
    """Escopo da execução autenticada; o agente não escolhe estes campos no catálogo."""

    run_id: UUID = Field(description="Execução autenticada à qual a chamada pertence.")
    process_id: Identifier = Field(description="Identificador do processo no escopo da execução.")
    corpus_version: Identifier = Field(description="Versão do corpus autorizado para a execução.")
    requirements_version: Identifier = Field(
        description="Versão do checklist associada ao processo."
    )


class InventoryItem(Contract):
    document_id: Identifier
    title: Text
    source: Text
    pages: StrictInt = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProcessResult(ToolContext):
    process: Process
    inventory: list[InventoryItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_process(self):
        if (
            self.process.process_id,
            self.process.corpus_version,
            self.process.requirements_version,
        ) != (self.process_id, self.corpus_version, self.requirements_version):
            raise ValueError("Process metadata must match the tool context.")
        if len({item.document_id for item in self.inventory}) != len(self.inventory):
            raise ValueError("Inventory document IDs must be unique.")
        return self


class SearchInput(ToolContext):
    """Busca literal de trechos no processo e corpus da execução."""

    query: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[^\x00]+$",
        description="Busca literal; U+0000 não é permitido.",
    )
    limit: StrictInt = Field(
        default=5, ge=1, le=20, description="Número máximo de trechos retornados; padrão 5."
    )


class SearchResult(ToolContext):
    export_completeness: Completeness
    items: list[Chunk] = Field(max_length=20)
    warning: str = "Não localizar um documento não prova ausência no processo original."

    @model_validator(mode="after")
    def consistent_chunks(self):
        if any(
            (item.process_id, item.corpus_version) != (self.process_id, self.corpus_version)
            for item in self.items
        ):
            raise ValueError("Search chunks must belong to the response context.")
        if len({item.chunk_id for item in self.items}) != len(self.items):
            raise ValueError("Search chunk IDs must be unique.")
        return self


class ReadInput(ToolContext):
    """Seleção de documento e, opcionalmente, de suas páginas."""

    document_id: Identifier = Field(description="Identificador de documento no corpus autorizado.")
    pages: list[StrictInt] | None = Field(
        default=None,
        min_length=1,
        description="Números de páginas positivas e distintas; omita ou use null para todas.",
    )

    @model_validator(mode="after")
    def valid_pages(self):
        if self.pages and (min(self.pages) < 1 or len(set(self.pages)) != len(self.pages)):
            raise ValueError("Páginas devem ser positivas e únicas.")
        return self


class DocumentResult(ToolContext):
    document: Document

    @model_validator(mode="after")
    def consistent_document(self):
        if (self.document.process_id, self.document.corpus_version) != (
            self.process_id,
            self.corpus_version,
        ):
            raise ValueError("Document must belong to the response context.")
        numbers = [page.number for page in self.document.pages]
        if numbers != sorted(numbers):
            raise ValueError("Document pages must follow their numeric order.")
        return self


class ToolError(Contract):
    code: ErrorCode
    message: str
    run_id: UUID | None = None
    retryable: StrictBool = False


class Requirement(Contract):
    requirement_id: Identifier
    description: Text
    source: Text


class RequirementsResult(ToolContext):
    items: list[Requirement] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_requirements(self):
        if len({item.requirement_id for item in self.items}) != len(self.items):
            raise ValueError("Checklist requirement IDs must be unique.")
        return self


class Evidence(Contract):
    """Referência verificável a um trecho e à página de origem no corpus."""

    document_id: Identifier = Field(description="Documento que contém o trecho citado.")
    chunk_id: Identifier = Field(description="Identificador do trecho citado nesse documento.")
    page: StrictInt = Field(
        ge=1, description="Número da página de origem do trecho, a partir de 1."
    )


class InventoryEvidence(Contract):
    """Referência ao inventário para fundamentar uma limitação da exportação."""

    kind: Literal["inventory"] = Field(
        default="inventory", description="Identifica referência ao inventário."
    )
    process_id: Identifier = Field(description="Processo a que o inventário pertence.")
    corpus_version: Identifier = Field(description="Versão do corpus a que o inventário pertence.")


class WriteInput(ToolContext):
    """Entrada comum de escrita fundamentada com chave para repetição idempotente."""

    idempotency_key: Identifier = Field(
        description="Chave da escrita; reutilize-a apenas com a mesma ferramenta "
        "e conteúdo da entrada."
    )
    content: Text = Field(description="Texto integral da minuta ou pendência a persistir.")
    evidence: list[Evidence | InventoryEvidence] = Field(
        min_length=1, description="Referências a trechos ou ao inventário que fundamentam o texto."
    )
    evidence_note: Text = Field(
        description="Explicação de como as referências fundamentam o texto."
    )


class PendencyInput(WriteInput):
    """Pendência associada a um requisito do checklist versionado."""

    requirement_id: Identifier = Field(
        description="Identificador do requisito no checklist da execução."
    )


class WriteReceipt(ToolContext):
    """Comprovante do artefato persistido, inclusive em repetição idempotente."""

    artifact_id: UUID = Field(description="Identificador do artefato persistido.")
    persisted_at: AwareDatetime = Field(
        description="Instante com fuso horário da persistência original."
    )
    content_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$", description="SHA-256 hexadecimal do texto persistido em UTF-8."
    )
    replayed: StrictBool = Field(description="Indica retorno de escrita idempotente anterior.")


class ArtifactResponse(Contract):
    artifact_id: UUID
    tool: Literal["registrar_pendencia", "salvar_minuta"]
    payload: PendencyInput | WriteInput
    receipt: WriteReceipt


class ToolCallRecord(Contract):
    """Chamada declarada no relatório experimental, sujeita à reconciliação do servidor."""

    tool_call_id: Identifier
    tool: ToolName
    duration_ms: StrictFloat = Field(ge=0)
    status: Literal["ok", "error"]
    artifact_id: Identifier | None = None


class ExperimentRun(ToolContext):
    contract_version: Literal["0.1"] = "0.1"
    task_id: Identifier
    split: Literal["development", "final"]
    executor: Literal["hermes", "langgraph", "simulation"]
    repetition: StrictInt = Field(ge=1)
    code_commit: Text
    harness_version: Text
    adapter_version: Text
    model: Text
    endpoint_id: Identifier
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: dict[ParameterName, NulFree | StrictFloat | StrictInt | StrictBool]
    started_at: datetime
    latency_ms: StrictFloat = Field(ge=0)
    tool_calls: list[ToolCallRecord]
    input_tokens: StrictInt | None = Field(default=None, ge=0)
    output_tokens: StrictInt | None = Field(default=None, ge=0)
    cost_usd: StrictFloat | None = Field(default=None, ge=0)
    agent_declared_success: StrictBool
    persisted_artifact_ids: list[Identifier]
    verified_success: StrictBool | None
    evaluator: NulFree | None


# Revisão de um ExperimentRun sem parameters.revision (ADR 011): o servidor grava como 1.
FIRST_REVISION = 1
# Chamadas lógicas que nunca chegaram ao servidor (P10): ficam fora de tool_calls e entram só
# como contagem em parameters, declarada pelo cliente comum; 0 explícito é diferente de ausente.
UNOBSERVED_PARAMETER = "unobserved_tool_calls"


def experiment_record(run: ExperimentRun) -> dict:
    """JSON comparável de um ExperimentRun, com ``parameters.revision`` padrão 1 (ADR 011).

    Regra única para servidor (``/experiments`` e resultado do run), ``ExperimentRunClient`` e
    ``RunBridge``: um relatório sem ``revision`` equivale à revisão 1 gravada.
    """
    value = run.model_dump(mode="json")
    value["parameters"].setdefault("revision", FIRST_REVISION)
    return value


class PhysicalToolPhase(Contract):
    """Fase registrada para uma requisição física; não comprova entrega ao cliente."""

    phase: Literal["started", "effect_confirmed", "completed", "failed", "interrupted"]
    recorded_at: StrictFloat
    artifact_id: UUID | None = None
    replayed: StrictBool | None = None


class PhysicalToolAttempt(Contract):
    """Registro de requisição física, que pode pertencer a uma chamada lógica."""

    attempt_id: UUID
    tool: ToolName
    method: str
    run_id: UUID | None = None
    tool_call_id: Identifier | None = None
    args_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    started_at: StrictFloat
    finished_at: StrictFloat | None = None
    response_state: Literal["started", "prepared", "interrupted"]
    http_status: StrictInt | None = Field(default=None, ge=100, le=599)
    code: str | None = None
    client_received: StrictBool | None = None
    phases: list[PhysicalToolPhase]

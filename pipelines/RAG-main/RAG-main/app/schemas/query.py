from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.config import EmbeddingSpec, RetrievalMode

PROCESS_PATTERN = r"[0-9]{5}-[0-9]{8}/[0-9]{4}-[0-9]{2}"
DOCUMENT_PATTERN = r"[0-9]{6,10}"
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
ProcessNumber = Annotated[str, StringConstraints(pattern=f"^{PROCESS_PATTERN}$")]
DocumentNumber = Annotated[str, StringConstraints(pattern=f"^{DOCUMENT_PATTERN}$")]


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Question
    top_k: int | None = Field(None, strict=True, ge=1, le=100)
    processo_sei: ProcessNumber | None = None
    documento_sei_id: DocumentNumber | None = None
    mode: RetrievalMode | None = None


class Evidence(BaseModel):
    chunk_id: str
    text: str
    processo_sei: str
    documento_sei_id: str | None
    tipo_documento: str | None
    arquivo_origem: str
    pagina_inicio: int
    pagina_fim: int
    paginas_origem: list[int]
    vector_score: float | None = None
    keyword_score: float | None = None
    exact_identifier_match: bool = False
    rrf_score: float | None = None
    rerank_score: float | None = None


class QueryResponse(BaseModel):
    mode: RetrievalMode
    top_k: int
    candidate_k: int
    rrf_k: int | None = None
    embedding: EmbeddingSpec
    reranker_model: str | None = None
    reranker_revision: str | None = None
    rerank_candidate_k: int | None = None
    rerank_max_tokens: int | None = None
    results: list[Evidence]

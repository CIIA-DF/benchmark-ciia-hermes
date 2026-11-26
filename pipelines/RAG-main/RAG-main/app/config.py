from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BGE_M3 = "BAAI/bge-m3"
MINILM = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BGE_RERANKER = "BAAI/bge-reranker-v2-m3"
RERANKER_REVISION = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"


@dataclass(frozen=True)
class EmbeddingSpec:
    model: str
    revision: str
    dimensions: int


EMBEDDING_DEFAULTS = {
    BGE_M3: EmbeddingSpec(BGE_M3, "5617a9f61b028005a4858fdac845db406aefb181", 1024),
    MINILM: EmbeddingSpec(MINILM, "e8f8c211226b894fcb81acc59f3b34ba3efd5f42", 384),
}


class RetrievalMode(StrEnum):
    DENSE = "dense"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RAG_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    database_url: SecretStr | None = None
    postgres_port: int = Field(5433, ge=1, le=65535)
    postgres_password: SecretStr | None = None

    chunk_tokens: int = Field(500, ge=1)
    chunk_overlap: int = Field(75, ge=0)
    embedding_model: str = BGE_M3
    embedding_revision: str | None = Field(None, pattern=r"^[0-9a-f]{40}$")
    embedding_dimensions: int | None = Field(None, ge=1, le=2000)
    embedding_batch_size: int = Field(4, ge=1)

    retrieval_mode: RetrievalMode = RetrievalMode.HYBRID
    candidate_k: int = Field(20, ge=1, le=100)
    top_k: int = Field(5, ge=1, le=100)
    rrf_k: int = Field(60, ge=1)
    rerank_enabled: bool = True
    rerank_model: str = BGE_RERANKER
    rerank_revision: str | None = Field(None, pattern=r"^[0-9a-f]{40}$")
    rerank_candidate_k: int = Field(20, ge=1, le=100)
    rerank_batch_size: int = Field(2, ge=1)
    rerank_max_tokens: int = Field(768, ge=8)

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError("RAG_CHUNK_OVERLAP deve ser menor que RAG_CHUNK_TOKENS.")
        if self.embedding_model not in EMBEDDING_DEFAULTS and (
            not self.embedding_revision or self.embedding_dimensions is None
        ):
            raise ValueError("Configure a revisão e a dimensão do modelo de embeddings.")
        if self.rerank_enabled and self.rerank_model != BGE_RERANKER and not self.rerank_revision:
            raise ValueError("Configure a revisão do modelo de reranking.")
        return self

    @property
    def embedding(self) -> EmbeddingSpec:
        default = EMBEDDING_DEFAULTS.get(self.embedding_model)
        revision = self.embedding_revision or (default.revision if default else None)
        dimensions = self.embedding_dimensions or (default.dimensions if default else None)
        assert revision is not None and dimensions is not None
        return EmbeddingSpec(self.embedding_model, revision, dimensions)

    def postgres_url(self) -> str | URL:
        if self.database_url:
            return self.database_url.get_secret_value()
        password = self.postgres_password.get_secret_value() if self.postgres_password else ""
        if not password:
            raise ValueError("Configure RAG_POSTGRES_PASSWORD ou RAG_DATABASE_URL.")
        return URL.create(
            "postgresql+psycopg",
            username="rag",
            password=password,
            host="127.0.0.1",
            port=self.postgres_port,
            database="rag",
        )

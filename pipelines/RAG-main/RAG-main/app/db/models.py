from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Computed, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Integer


class Base(DeclarativeBase):
    pass


class IndexProfile(Base):
    __tablename__ = "rag_index_profile"
    __table_args__ = (
        CheckConstraint("id = 1"),
        CheckConstraint("dimensions BETWEEN 1 AND 2000"),
        CheckConstraint("chunk_overlap >= 0 AND chunk_tokens > chunk_overlap"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(Text)
    revision: Mapped[str] = mapped_column(Text)
    dimensions: Mapped[int]
    chunk_tokens: Mapped[int]
    chunk_overlap: Mapped[int]


class Process(Base):
    __tablename__ = "rag_processes"

    processo_sei: Mapped[str] = mapped_column(Text, primary_key=True)


class Document(Base):
    __tablename__ = "rag_documents"
    __table_args__ = (
        UniqueConstraint("processo_sei", "arquivo_origem", "pagina_inicio"),
        CheckConstraint("pagina_inicio > 0 AND pagina_fim >= pagina_inicio"),
    )

    document_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    processo_sei: Mapped[str] = mapped_column(
        ForeignKey("rag_processes.processo_sei", ondelete="CASCADE")
    )
    arquivo_origem: Mapped[str] = mapped_column(Text)
    documento_sei_id: Mapped[str | None] = mapped_column(Text, index=True)
    tipo_documento: Mapped[str | None] = mapped_column(Text)
    pagina_inicio: Mapped[int]
    pagina_fim: Mapped[int]
    parser_metadata: Mapped[dict] = mapped_column(JSONB)


class Chunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        CheckConstraint("token_count > 0 AND cardinality(paginas_origem) > 0"),
        Index("rag_chunks_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_key: Mapped[str] = mapped_column(
        ForeignKey("rag_documents.document_key", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    paginas_origem: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    token_count: Mapped[int]
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('portuguese'::regconfig, text)", persisted=True)
    )


class Embedding(Base):
    __tablename__ = "rag_embeddings"

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey("rag_chunks.chunk_id", ondelete="CASCADE"), primary_key=True
    )
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("rag_index_profile.id"), index=True, server_default="1"
    )
    # O CHECK e o HNSW dimensional são criados para o perfil ativo na inicialização.
    vector: Mapped[list[float]] = mapped_column(Vector())

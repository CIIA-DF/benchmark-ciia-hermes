from sqlalchemy import create_engine, make_url, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Base, IndexProfile


class IndexConfigurationError(RuntimeError):
    """O banco precisa ser preparado com a configuração ativa."""


def create_database_engine(settings: Settings) -> Engine:
    try:
        url = make_url(settings.postgres_url())
    except ArgumentError:
        raise ValueError("URL do banco RAG inválida.") from None
    if url.drivername != "postgresql+psycopg":
        raise ValueError("A URL do RAG deve usar postgresql+psycopg.")
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=0,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


def profile_values(settings: Settings) -> dict:
    spec = settings.embedding
    return {
        "model": spec.model,
        "revision": spec.revision,
        "dimensions": spec.dimensions,
        "chunk_tokens": settings.chunk_tokens,
        "chunk_overlap": settings.chunk_overlap,
    }


def require_profile(session: Session, settings: Settings, *, lock: bool = False) -> None:
    statement = select(IndexProfile).where(IndexProfile.id == 1)
    if lock:
        statement = statement.with_for_update()
    profile = session.scalar(statement)
    if profile is None or any(
        getattr(profile, field) != value for field, value in profile_values(settings).items()
    ):
        raise IndexConfigurationError(
            "Perfil do índice ausente ou incompatível. Inicialize um banco para esta configuração."
        )


def initialize_database(engine: Engine, settings: Settings) -> None:
    dimensions = settings.embedding.dimensions
    with Session(engine) as session, session.begin():
        # Serializa inicializações concorrentes antes de consultar/criar o esquema.
        session.execute(text("SELECT pg_advisory_xact_lock(1849337031)"))
        session.execute(text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"))
        Base.metadata.create_all(session.connection())
        if session.get(IndexProfile, 1) is None:
            session.add(IndexProfile(id=1, **profile_values(settings)))
            session.execute(
                text(
                    "ALTER TABLE rag_embeddings ADD CONSTRAINT rag_embedding_dimensions "
                    f"CHECK (vector_dims(vector) = {dimensions})"
                )
            )
            session.execute(
                text(
                    "CREATE INDEX rag_embeddings_cosine_hnsw ON rag_embeddings "
                    f"USING hnsw ((vector::vector({dimensions})) vector_cosine_ops)"
                )
            )
        else:
            require_profile(session, settings)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine)

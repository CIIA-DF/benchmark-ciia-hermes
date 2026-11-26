from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import RERANKER_REVISION, RetrievalMode, Settings
from app.db.session import IndexConfigurationError, require_profile
from app.ingestion.embeddings import Embedder, EmbeddingEncoder
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.keyword_search import keyword_search
from app.retrieval.rerank import CrossEncoderScorer, PairScorer, rerank
from app.retrieval.vector_search import vector_search
from app.schemas.query import QueryRequest, QueryResponse


class RetrievalService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        encoder: EmbeddingEncoder | None = None,
        scorer: PairScorer | None = None,
    ):
        self.sessions = sessions
        self.settings = settings
        self.encoder = encoder if encoder is not None else Embedder(settings)
        self.scorer = scorer if scorer is not None else CrossEncoderScorer(settings)
        if self.encoder.spec != settings.embedding:
            raise ValueError("O encoder precisa corresponder ao perfil configurado.")

    def ready(self) -> bool:
        try:
            with self.sessions() as session:
                require_profile(session, self.settings)
        except (IndexConfigurationError, SQLAlchemyError):
            return False
        return True

    def query(self, request: QueryRequest) -> QueryResponse:
        settings = self.settings
        top_k = request.top_k or settings.top_k
        mode = request.mode or settings.retrieval_mode
        if mode == RetrievalMode.HYBRID_RERANK and not settings.rerank_enabled:
            mode = RetrievalMode.HYBRID
        rerank_enabled = mode == RetrievalMode.HYBRID_RERANK
        rerank_limit = max(settings.rerank_candidate_k, top_k)
        candidate_k = (
            top_k
            if mode == RetrievalMode.DENSE
            else max(settings.candidate_k, rerank_limit if rerank_enabled else top_k)
        )

        with self.sessions() as session:
            # Cada ranking vê a mesma versão dos documentos, ainda que um build faça commit.
            session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            require_profile(session, settings)
            results = vector_search(session, request, self.encoder, candidate_k)
            if mode != RetrievalMode.DENSE:
                lexical = keyword_search(session, request, candidate_k)
                results = reciprocal_rank_fusion(results, lexical, k=settings.rrf_k)

        if rerank_enabled:
            results = rerank(request.question, results, self.scorer, rerank_limit, top_k)

        return QueryResponse(
            mode=mode,
            top_k=top_k,
            candidate_k=candidate_k,
            rrf_k=settings.rrf_k if mode != RetrievalMode.DENSE else None,
            embedding=self.encoder.spec,
            reranker_model=settings.rerank_model if rerank_enabled else None,
            reranker_revision=(settings.rerank_revision or RERANKER_REVISION)
            if rerank_enabled
            else None,
            rerank_candidate_k=rerank_limit if rerank_enabled else None,
            rerank_max_tokens=settings.rerank_max_tokens if rerank_enabled else None,
            results=results[:top_k],
        )

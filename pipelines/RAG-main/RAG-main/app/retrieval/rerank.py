import math
from collections.abc import Callable
from threading import Lock

from app.config import RERANKER_REVISION, Settings
from app.ingestion.embeddings import ModelError
from app.schemas.query import Evidence

PairScorer = Callable[[list[tuple[str, str]]], list[float]]


class CrossEncoderScorer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.revision = settings.rerank_revision or RERANKER_REVISION
        self._lock = Lock()
        self._model = None

    def __call__(self, pairs: list[tuple[str, str]]) -> list[float]:
        try:
            from sentence_transformers import CrossEncoder
            from torch.nn import Identity

            with self._lock:
                if self._model is None:
                    self._model = CrossEncoder(
                        self.settings.rerank_model,
                        revision=self.revision,
                        device="cpu",
                        max_length=self.settings.rerank_max_tokens,
                        model_kwargs={"use_safetensors": True},
                    )
                return self._model.predict(
                    pairs,
                    batch_size=self.settings.rerank_batch_size,
                    activation_fn=Identity(),
                    show_progress_bar=False,
                ).tolist()
        except Exception as exc:
            raise ModelError("Falha ao executar o reranker local.") from exc


def rerank(
    question: str, candidates: list[Evidence], scorer: PairScorer, limit: int, top_k: int
) -> list[Evidence]:
    shortlist = candidates[:limit]
    if not shortlist:
        return []
    scores = scorer([(question, candidate.text) for candidate in shortlist])
    if len(scores) != len(shortlist) or not all(math.isfinite(score) for score in scores):
        raise ModelError("O reranker retornou pontuações inválidas.")
    return [
        candidate.model_copy(update={"rerank_score": score})
        for candidate, score in sorted(
            zip(shortlist, scores, strict=True), key=lambda item: -item[1]
        )[:top_k]
    ]

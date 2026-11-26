import math
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from app.config import EmbeddingSpec, Settings


class EmbeddingEncoder(Protocol):
    spec: EmbeddingSpec

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class ModelError(RuntimeError):
    """Falha de carregamento, inferência ou configuração do modelo."""


@dataclass
class Embedder:
    settings: Settings

    def __post_init__(self) -> None:
        self.spec = self.settings.embedding
        self._lock = Lock()
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(
                    self.spec.model,
                    revision=self.spec.revision,
                    device="cpu",
                )
                if model.get_embedding_dimension() != self.spec.dimensions:
                    raise ModelError("Dimensão do modelo diverge da configuração.")
                if not model.tokenizer.is_fast:
                    raise ModelError("O chunking requer um tokenizador rápido com offsets.")
                model_limit = model.max_seq_length - model.tokenizer.num_special_tokens_to_add()
                if self.settings.chunk_tokens > model_limit:
                    raise ModelError(f"RAG_CHUNK_TOKENS excede o limite do modelo ({model_limit}).")
                self._model = model
            except ModelError:
                raise
            except Exception as exc:
                raise ModelError("Falha ao carregar o modelo local de embeddings.") from exc
        return self._model

    def token_offsets(self, text: str) -> list[tuple[int, int]]:
        with self._lock:
            model = self._load()
            tokenization = model.tokenizer(
                text,
                add_special_tokens=False,
                return_offsets_mapping=True,
                truncation=False,
                verbose=False,
            )
        return [(start, end) for start, end in tokenization["offset_mapping"] if start < end]

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        with self._lock:
            model = self._load()
            try:
                vectors = model.encode(
                    texts,
                    batch_size=self.settings.embedding_batch_size,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                ).tolist()
            except Exception as exc:
                raise ModelError("Falha ao gerar embeddings locais.") from exc
        if len(vectors) != len(texts) or any(
            len(vector) != self.spec.dimensions
            or not all(math.isfinite(value) for value in vector)
            or not any(vector)
            for vector in vectors
        ):
            raise ModelError("O modelo retornou embeddings incompatíveis com a busca cosseno.")
        return vectors

from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, text
from sqlalchemy.orm import Session

from app.db.models import Chunk, Embedding
from app.ingestion.embeddings import EmbeddingEncoder
from app.retrieval.candidates import candidate_query, evidence_from_row
from app.schemas.query import Evidence, QueryRequest


def vector_search(
    session: Session, request: QueryRequest, encoder: EmbeddingEncoder, top_k: int
) -> list[Evidence]:
    vector = encoder.encode([request.question])[0]
    distance = cast(Embedding.vector, Vector(encoder.spec.dimensions)).cosine_distance(vector)
    statement = (
        candidate_query(request)
        .join(Embedding, Embedding.chunk_id == Chunk.chunk_id)
        .add_columns((1 - distance).label("vector_score"))
        .order_by(distance)
        .limit(top_k)
    )
    session.execute(text("SET LOCAL hnsw.iterative_scan = 'strict_order'"))
    results = [evidence_from_row(row) for row in session.execute(statement).mappings()]
    return sorted(results, key=lambda hit: (-hit.vector_score, hit.chunk_id))

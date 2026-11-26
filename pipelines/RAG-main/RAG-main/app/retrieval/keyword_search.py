import re

from sqlalchemy import case, false, func, literal_column, or_
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.retrieval.candidates import candidate_query, evidence_from_row
from app.schemas.query import DOCUMENT_PATTERN, PROCESS_PATTERN, Evidence, QueryRequest

PROCESS_RE = re.compile(rf"\b{PROCESS_PATTERN}\b")
DOCUMENT_RE = re.compile(rf"\b{DOCUMENT_PATTERN}\b")


def keyword_search(session: Session, request: QueryRequest, top_k: int) -> list[Evidence]:
    processes = set(PROCESS_RE.findall(request.question))
    documents = set(DOCUMENT_RE.findall(PROCESS_RE.sub(" ", request.question)))
    exact_process = Document.processo_sei.in_(processes) if processes else false()
    exact_document = (
        Document.documento_sei_id.is_not(None) & Document.documento_sei_id.in_(documents)
        if documents
        else false()
    )
    exact = or_(exact_document, exact_process)

    query = func.websearch_to_tsquery(literal_column("'portuguese'::regconfig"), request.question)
    matches = Chunk.search_vector.bool_op("@@")(query)
    rank = func.ts_rank_cd(Chunk.search_vector, query)
    statement = (
        candidate_query(request)
        .add_columns(rank.label("keyword_score"), exact.label("exact_identifier_match"))
        .where(or_(exact, matches))
        .order_by(
            case((exact_document, 2), (exact_process, 1), else_=0).desc(),
            rank.desc(),
            Chunk.chunk_id,
        )
        .limit(top_k)
    )
    return [evidence_from_row(row) for row in session.execute(statement).mappings()]

from sqlalchemy import select

from app.db.models import Chunk, Document
from app.schemas.query import Evidence, QueryRequest


def candidate_query(request: QueryRequest):
    statement = (
        select(
            Chunk.chunk_id,
            Chunk.text,
            Chunk.paginas_origem,
            Document.processo_sei,
            Document.documento_sei_id,
            Document.tipo_documento,
            Document.arquivo_origem,
        )
        .select_from(Chunk)
        .join(Document)
    )
    if request.processo_sei is not None:
        statement = statement.where(Document.processo_sei == request.processo_sei)
    if request.documento_sei_id is not None:
        statement = statement.where(Document.documento_sei_id == request.documento_sei_id)
    return statement


def evidence_from_row(row) -> Evidence:
    return Evidence(
        **row,
        pagina_inicio=row["paginas_origem"][0],
        pagina_fim=row["paginas_origem"][-1],
    )

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import IndexConfigurationError
from app.ingestion.embeddings import ModelError
from app.schemas.query import QueryRequest, QueryResponse

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    if not request.app.state.retrieval.ready():
        raise HTTPException(503, "Índice indisponível ou incompatível.")
    return {"status": "ok"}


@router.post("/api/query")
def query(payload: QueryRequest, request: Request) -> QueryResponse:
    try:
        return request.app.state.retrieval.query(payload)
    except (IndexConfigurationError, SQLAlchemyError):
        raise HTTPException(503, "Índice indisponível ou incompatível.") from None
    except ModelError:
        raise HTTPException(503, "Modelo local de recuperação indisponível.") from None

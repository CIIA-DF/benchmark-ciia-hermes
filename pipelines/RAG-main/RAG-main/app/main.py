from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.engine import Engine

from app.api.routes.query import router
from app.config import Settings
from app.db.session import create_database_engine, session_factory
from app.retrieval.service import RetrievalService


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    active_settings = settings if settings is not None else Settings()
    database = engine if engine is not None else create_database_engine(active_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if engine is not None:
            yield
            return
        try:
            yield
        finally:
            database.dispose()

    app = FastAPI(title="RAG SEI — Evidências", version="0.1.0", lifespan=lifespan)
    app.state.retrieval = RetrievalService(session_factory(database), active_settings)
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid_query(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})

    return app

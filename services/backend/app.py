"""API local de consulta. Ferramentas de escrita ainda não estão implementadas."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import (
    DocumentResult,
    ProcessResult,
    ReadInput,
    SearchInput,
    SearchResult,
    ToolContext,
    ToolError,
    WriteInput,
)
from services.backend.storage import chunks, documents, initialize, make_engine, processes

logger = logging.getLogger(__name__)


class ToolFailure(Exception):
    def __init__(self, status: int, error: ToolError):
        self.status = status
        self.error = error


def create_app(engine: Engine | None = None) -> FastAPI:
    database = engine if engine is not None else make_engine()

    @asynccontextmanager
    async def lifespan(_app):
        initialize(database)
        yield
        database.dispose()

    app = FastAPI(title="CIIA — ferramentas experimentais", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(ToolFailure)
    async def tool_failure(_request: Request, exc: ToolFailure):
        return JSONResponse(status_code=exc.status, content=exc.error.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        # Não ecoar entradas, documentos ou credenciais na resposta/log.
        return JSONResponse(
            status_code=422,
            content=ToolError(
                code="validation_error", message="Entrada inválida; consulte o contrato em /docs."
            ).model_dump(mode="json"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(_request: Request, _exc: SQLAlchemyError):
        logger.error("storage_unavailable")
        return JSONResponse(
            status_code=503,
            content=ToolError(
                code="storage_unavailable",
                message="Banco indisponível.",
                retryable=True,
            ).model_dump(mode="json"),
        )

    def get_process(context: ToolContext):
        with database.connect() as connection:
            result = connection.execute(
                select(processes.c.payload).where(
                    processes.c.process_id == context.process_id,
                    processes.c.corpus_version == context.corpus_version,
                )
            ).scalar_one_or_none()
        if result is None:
            raise ToolFailure(
                404,
                ToolError(
                    code="not_found",
                    message="Processo/corpus não encontrado na base experimental.",
                    run_id=context.run_id,
                ),
            )
        if result["requirements_version"] != context.requirements_version:
            raise ToolFailure(
                409,
                ToolError(
                    code="version_mismatch",
                    message="Versão dos requisitos incompatível.",
                    run_id=context.run_id,
                ),
            )
        return result

    @app.get("/health")
    def health():
        with database.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "contract_version": "0.1"}

    @app.post("/tools/consultar_processo", response_model=ProcessResult)
    def consultar_processo(context: ToolContext):
        return ProcessResult(**context.model_dump(), process=get_process(context))

    @app.post("/tools/buscar_documentos", response_model=SearchResult)
    def buscar_documentos(query: SearchInput):
        process = get_process(query)
        with database.connect() as connection:
            rows = (
                connection.execute(
                    select(chunks.c.payload)
                    .where(
                        chunks.c.process_id == query.process_id,
                        chunks.c.corpus_version == query.corpus_version,
                        chunks.c.text.icontains(query.query, autoescape=True),
                    )
                    .order_by(chunks.c.document_id, chunks.c.chunk_id)
                    .limit(query.limit)
                )
                .scalars()
                .all()
            )
        return SearchResult(
            **query.model_dump(include=set(ToolContext.model_fields)),
            export_completeness=process["export_completeness"],
            items=rows,
        )

    @app.post("/tools/ler_documento", response_model=DocumentResult)
    def ler_documento(query: ReadInput):
        get_process(query)
        with database.connect() as connection:
            result = connection.execute(
                select(documents.c.payload).where(
                    documents.c.process_id == query.process_id,
                    documents.c.corpus_version == query.corpus_version,
                    documents.c.document_id == query.document_id,
                )
            ).scalar_one_or_none()
        if result is None:
            raise ToolFailure(
                404,
                ToolError(
                    code="not_found",
                    message="Documento não encontrado neste processo/corpus.",
                    run_id=query.run_id,
                ),
            )
        return DocumentResult(
            **query.model_dump(include=set(ToolContext.model_fields)), document=result
        )

    def planned(context: ToolContext):
        raise ToolFailure(
            501,
            ToolError(
                code="not_implemented",
                message="Contrato previsto; ferramenta ainda não implementada.",
                run_id=context.run_id,
            ),
        )

    @app.post("/tools/consultar_requisitos", response_model=ToolError, status_code=501)
    def consultar_requisitos(context: ToolContext):
        planned(context)

    @app.post("/tools/registrar_pendencia", response_model=ToolError, status_code=501)
    def registrar_pendencia(context: WriteInput):
        planned(context)

    @app.post("/tools/salvar_minuta", response_model=ToolError, status_code=501)
    def salvar_minuta(context: WriteInput):
        planned(context)

    return app

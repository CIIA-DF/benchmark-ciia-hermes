"""API autenticada de tools, conversas, execuções e eventos duráveis."""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from contracts.execution import (
    AgentEvent,
    AgentResult,
    CapabilitiesResponse,
    ClaimedRun,
    ClaimInput,
    ConversationDetail,
    ConversationInput,
    ConversationResponse,
    EventReceipt,
    HeartbeatResponse,
    MessageInput,
    RunInput,
    RunResponse,
)
from contracts.models import (
    ArtifactResponse,
    DocumentResult,
    PendencyInput,
    Process,
    ProcessResult,
    ReadInput,
    RequirementsResult,
    SearchInput,
    SearchResult,
    ToolContext,
    ToolError,
    WriteInput,
    WriteReceipt,
)
from services.backend.auth import authenticate, bootstrap
from services.backend.errors import ToolFailure, fail
from services.backend.execution import TERMINAL, ExecutionService
from services.backend.storage import initialize, make_engine
from services.backend.tools import ToolService

logger = logging.getLogger(__name__)

ERRORS = {
    401: "Credencial ausente ou inválida (`unauthorized`).",
    403: "Perfil, concessão de processo/corpus, reserva ou contexto incompatível (`forbidden`).",
    404: "Recurso inexistente ou fora do alcance do perfil (`not_found`).",
    409: "Conflito de estado, idempotência ou versão "
    "(`conflict`, `idempotency_conflict`, `version_mismatch`).",
    422: "Entrada inválida ou limite excedido (`validation_error`, `context_limit`).",
    503: "Banco ou executor indisponível (`storage_unavailable`, `executor_unavailable`).",
}


def errors(*statuses):
    return {status: {"model": ToolError, "description": ERRORS[status]} for status in statuses}


def camel_id(route):
    head, *rest = route.name.split("_")
    return head + "".join(part.title() for part in rest)


SSE_EXAMPLE = (
    'id: 3\nevent: text_delta\ndata: {"text": "Resposta parcial"}\n\n'
    'id: 4\nevent: done\ndata: {"status": "succeeded"}\n\n'
)


def create_app(engine: Engine | None = None) -> FastAPI:
    database = engine if engine is not None else make_engine()
    service = ExecutionService(database)
    tools = ToolService(service)

    @asynccontextmanager
    async def lifespan(_app):
        initialize(database)
        bootstrap(database)
        yield
        database.dispose()

    app = FastAPI(
        title="CIIA — tools e conversas experimentais",
        version="0.2.0",
        lifespan=lifespan,
        generate_unique_id_function=camel_id,
    )
    app.state.execution = service

    @app.exception_handler(ToolFailure)
    async def tool_failure(_request: Request, exc: ToolFailure):
        return JSONResponse(status_code=exc.status, content=exc.error.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
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
                code="storage_unavailable", message="Banco indisponível.", retryable=True
            ).model_dump(mode="json"),
        )

    def actor(request):
        return authenticate(database, request.headers.get("authorization"))

    def lease(request):
        return request.headers.get("x-run-token")

    health_schema = {
        "type": "object",
        "required": ["status", "contract_version"],
        "properties": {
            "status": {"const": "ok"},
            "contract_version": {"type": "string", "examples": ["0.2"]},
        },
    }

    @app.get(
        "/health",
        tags=["Saúde"],
        summary="Verifica API e banco",
        responses={
            200: {"content": {"application/json": {"schema": health_schema}}},
            **errors(503),
        },
    )
    def health():
        with database.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "contract_version": "0.2"}

    @app.get(
        "/capabilities",
        response_model=CapabilitiesResponse,
        tags=["Operador"],
        summary="Executores disponíveis e permissão de escrita do operador",
        responses=errors(401, 403, 503),
    )
    def capabilities(request: Request):
        profile = actor(request)
        service.operator(profile)
        return {
            "executors": [
                {
                    "name": name,
                    "available": name in service.enabled,
                    "simulation": name == "simulation",
                }
                for name in ("simulation", "hermes", "langgraph")
            ],
            "can_write": profile["can_write"],
            "profile": profile["principal_id"],
        }

    @app.get(
        "/processos",
        response_model=list[Process],
        tags=["Operador"],
        summary="Processos e corpus concedidos ao operador",
        responses=errors(401, 403, 503),
    )
    def list_processes(request: Request):
        return service.list_processes(actor(request))

    @app.post(
        "/conversations",
        status_code=201,
        response_model=ConversationResponse,
        tags=["Conversas"],
        summary="Cria conversa fixando processo, corpus, requisitos e executor",
        responses=errors(401, 403, 404, 409, 422, 503),
    )
    def create_conversation(value: ConversationInput, request: Request):
        return service.create_conversation(actor(request), value)

    @app.get(
        "/conversations",
        response_model=list[ConversationResponse],
        tags=["Conversas"],
        summary="Lista conversas do operador; filtro de participante não concede acesso",
        responses=errors(401, 403, 422, 503),
    )
    def list_conversations(request: Request, participant_id: UUID | None = None):
        return service.list_conversations(actor(request), participant_id)

    @app.get(
        "/conversations/{conversation_id}",
        response_model=ConversationDetail,
        tags=["Conversas"],
        summary="Conversa com mensagens e execuções",
        responses=errors(401, 403, 404, 422, 503),
    )
    def get_conversation(conversation_id: UUID, request: Request):
        return service.get_conversation(actor(request), str(conversation_id))

    @app.post(
        "/conversations/{conversation_id}/messages",
        status_code=202,
        response_model=RunResponse,
        tags=["Conversas"],
        summary="Envia mensagem e enfileira execução de chat",
        description="Repetir a mesma `idempotency_key` com a mesma entrada devolve o run "
        "existente. Só um run ativo por conversa; outro envio recebe 409 `conflict`.",
        responses=errors(401, 403, 404, 409, 422, 503),
    )
    def send_message(conversation_id: UUID, value: MessageInput, request: Request):
        return service.create_run(actor(request), value, str(conversation_id))

    @app.post(
        "/runs",
        status_code=202,
        response_model=RunResponse,
        tags=["Execuções"],
        summary="Enfileira execução de benchmark, sem memória de chat",
        responses=errors(401, 403, 404, 409, 422, 503),
    )
    def create_run(value: RunInput, request: Request):
        return service.create_run(actor(request), value)

    @app.post(
        "/runs/claim",
        response_model=ClaimedRun,
        tags=["Worker"],
        summary="Reserva a próxima execução do executor",
        description="Devolve `run_token`, que deve ir no cabeçalho `X-Run-Token` das tools, "
        "eventos, heartbeat e resultado.",
        responses={204: {"description": "Sem tarefa"}, **errors(401, 403, 422, 503)},
    )
    def claim_run(value: ClaimInput, request: Request):
        result = service.claim(actor(request), value.executor, value.run_id)
        return result if result is not None else Response(status_code=204)

    @app.get(
        "/runs/{run_id}",
        response_model=RunResponse,
        tags=["Execuções"],
        summary="Snapshot consistente de status, texto parcial e cursor",
        responses=errors(401, 403, 404, 422, 503),
    )
    def get_run(run_id: UUID, request: Request):
        return service.get_run(actor(request), str(run_id))

    @app.post(
        "/runs/{run_id}/heartbeat",
        response_model=HeartbeatResponse,
        tags=["Worker"],
        summary="Renova a reserva da execução",
        responses=errors(401, 403, 409, 422, 503),
    )
    def heartbeat(run_id: UUID, request: Request):
        return service.heartbeat(actor(request), str(run_id), lease(request))

    @app.post(
        "/runs/{run_id}/events",
        response_model=EventReceipt,
        tags=["Worker"],
        summary="Publica status ou trecho de resposta; idempotente por event_id",
        responses=errors(401, 403, 409, 422, 503),
    )
    def publish_event(run_id: UUID, value: AgentEvent, request: Request):
        return service.add_event(actor(request), str(run_id), lease(request), value)

    @app.post(
        "/runs/{run_id}/result",
        response_model=RunResponse,
        tags=["Worker"],
        summary="Encerra a execução com resultado final",
        description="Com sucesso, `answer` deve coincidir com a concatenação dos `text_delta`. "
        "Benchmark bem-sucedido exige `experiment`. Repetir o mesmo resultado é idempotente.",
        responses=errors(401, 403, 409, 422, 503),
    )
    def finish_run(run_id: UUID, value: AgentResult, request: Request):
        return service.finish(actor(request), str(run_id), lease(request), value)

    @app.get(
        "/runs/{run_id}/events",
        tags=["Execuções"],
        summary="Fluxo SSE de eventos persistidos",
        description="Eventos `status`, `text_delta`, `tool` e `done`, cada um com `id` igual à "
        "sequência. O cabeçalho `Last-Event-ID` tem precedência sobre `after`. Falhas após "
        "o início do fluxo chegam como evento `stream_error` com `message` e `code`. O fluxo "
        "termina após o evento `done`.",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "text/event-stream",
                "content": {
                    "text/event-stream": {"schema": {"type": "string"}, "example": SSE_EXAMPLE}
                },
            },
            **errors(401, 403, 404, 422, 503),
        },
        openapi_extra={
            "parameters": [
                {
                    "name": "Last-Event-ID",
                    "in": "header",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 0},
                    "description": "Última sequência recebida; substitui `after`.",
                }
            ]
        },
    )
    async def stream_events(run_id: UUID, request: Request, after: int = 0):
        profile = await run_in_threadpool(actor, request)
        try:
            cursor = int(request.headers.get("last-event-id", str(after)))
            if cursor < 0:
                raise ValueError
        except ValueError:
            fail(422, "validation_error", "Cursor de eventos inválido.")
        await run_in_threadpool(service.get_run, profile, str(run_id))

        async def generate():
            nonlocal cursor
            last_ping = time.monotonic()
            while not await request.is_disconnected():
                try:
                    current = await run_in_threadpool(actor, request)
                    items, status = await run_in_threadpool(
                        service.read_events, current, str(run_id), cursor
                    )
                except (ToolFailure, SQLAlchemyError) as exc:
                    code = exc.error.code if isinstance(exc, ToolFailure) else "storage_unavailable"
                    logger.warning("stream_interrupted run_id=%s code=%s", run_id, code)
                    payload = json.dumps({"message": "Fluxo interrompido.", "code": code})
                    yield f"event: stream_error\ndata: {payload}\n\n"
                    return
                for item in items:
                    cursor = item["sequence"]
                    data = json.dumps(item["payload"], ensure_ascii=False)
                    yield f"id: {cursor}\nevent: {item['kind']}\ndata: {data}\n\n"
                if status in TERMINAL and len(items) < 100:
                    return
                if time.monotonic() - last_ping > 10:
                    yield ": heartbeat\n\n"
                    last_ping = time.monotonic()
                await asyncio.sleep(0.2)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-store",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get(
        "/artifacts/{artifact_id}",
        response_model=ArtifactResponse,
        tags=["Artefatos"],
        summary="Artefato gravado e recibo, para conferência pelo operador",
        responses=errors(401, 403, 404, 422, 503),
    )
    def get_artifact(artifact_id: UUID, request: Request):
        return service.get_artifact(actor(request), str(artifact_id))

    tool_errors = errors(401, 403, 404, 409, 422, 503)

    @app.post(
        "/tools/consultar_processo",
        response_model=ProcessResult,
        tags=["Tools"],
        summary="Metadados, inventário e cobertura da exportação",
        responses=tool_errors,
    )
    def consultar_processo(value: ToolContext, request: Request):
        return tools.call("consultar_processo", actor(request), value, lease(request))

    @app.post(
        "/tools/buscar_documentos",
        response_model=SearchResult,
        tags=["Tools"],
        summary="Busca literal de trechos com fonte",
        description="Lista vazia não prova ausência no processo original.",
        responses=tool_errors,
    )
    def buscar_documentos(value: SearchInput, request: Request):
        return tools.call("buscar_documentos", actor(request), value, lease(request))

    @app.post(
        "/tools/ler_documento",
        response_model=DocumentResult,
        tags=["Tools"],
        summary="Lê documento inteiro ou páginas específicas",
        responses=tool_errors,
    )
    def ler_documento(value: ReadInput, request: Request):
        return tools.call("ler_documento", actor(request), value, lease(request))

    @app.post(
        "/tools/consultar_requisitos",
        response_model=RequirementsResult,
        tags=["Tools"],
        summary="Checklist versionado do processo",
        responses=tool_errors,
    )
    def consultar_requisitos(value: ToolContext, request: Request):
        return tools.call("consultar_requisitos", actor(request), value, lease(request))

    @app.post(
        "/tools/registrar_pendencia",
        response_model=WriteReceipt,
        tags=["Tools"],
        summary="Registra pendência de requisito com evidências",
        description="Replay com a mesma `idempotency_key` e entrada devolve o recibo com "
        "`replayed: true`; entrada diferente recebe 409 `idempotency_conflict`.",
        responses=tool_errors,
    )
    def registrar_pendencia(value: PendencyInput, request: Request):
        return tools.call("registrar_pendencia", actor(request), value, lease(request))

    @app.post(
        "/tools/salvar_minuta",
        response_model=WriteReceipt,
        tags=["Tools"],
        summary="Persiste minuta fundamentada e devolve recibo",
        description="Mesma regra de idempotência de `registrar_pendencia`.",
        responses=tool_errors,
    )
    def salvar_minuta(value: WriteInput, request: Request):
        return tools.call("salvar_minuta", actor(request), value, lease(request))

    def openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("components", {})["securitySchemes"] = {
            "BearerAuth": {"type": "http", "scheme": "bearer"},
            "RunToken": {"type": "apiKey", "in": "header", "name": "X-Run-Token"},
        }
        for path, methods in schema["paths"].items():
            for method, operation in methods.items():
                if not isinstance(operation, dict):
                    continue
                security = {"BearerAuth": []}
                if path.startswith("/tools/") or (
                    path
                    in {
                        "/runs/{run_id}/events",
                        "/runs/{run_id}/result",
                        "/runs/{run_id}/heartbeat",
                    }
                    and method == "post"
                ):
                    security["RunToken"] = []
                operation["security"] = [] if path == "/health" else [security]
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
    return app

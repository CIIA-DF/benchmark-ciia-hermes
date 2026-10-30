"""API autenticada de tools, conversas, execuções e eventos duráveis."""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from copy import deepcopy
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from contracts.catalog import TOOLS
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
    HealthResponse,
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
from services.backend.http_boundary import HTTPBoundary
from services.backend.storage import initialize, make_engine
from services.backend.streaming import LeasedStreamingResponse
from services.backend.tools import CALL_ID, ToolService

logger = logging.getLogger(__name__)

ERRORS = {
    500: "Saída inválida (`invalid_response`) ou falha interna (`internal_error`), sem detalhes.",
    401: "Credencial ausente ou inválida (`unauthorized`).",
    403: "Perfil, concessão de processo/corpus, reserva ou contexto incompatível (`forbidden`).",
    404: "Recurso inexistente ou fora do alcance do perfil (`not_found`).",
    409: "Conflito de estado, idempotência, versão ou orçamento "
    "(`conflict`, `idempotency_conflict`, `version_mismatch`, `budget_exceeded`).",
    422: "Entrada inválida ou limite excedido (`validation_error`, `context_limit`).",
    429: "Quota atingida (`resource_limit`); consulte retryable e o snapshot antes de repetir.",
    503: "Banco ou executor indisponível (`storage_unavailable`, `executor_unavailable`).",
}


def errors(*statuses):
    return {status: {"model": ToolError, "description": ERRORS[status]} for status in statuses}


def camel_id(route):
    head, *rest = route.name.split("_")
    return head + "".join(part.title() for part in rest)


TOOL_CALL_HEADER = {
    "name": "X-Tool-Call-Id",
    "in": "header",
    "required": False,
    "schema": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]{1,120}$"},
    "description": "ID da chamada lógica, repetido nas retentativas; ausente, o servidor gera. "
    "Correlaciona o histórico de tentativas com `ExperimentRun.tool_calls`.",
}

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
        version="0.3.0",
        lifespan=lifespan,
        generate_unique_id_function=camel_id,
    )
    app.state.execution = service
    app.add_middleware(HTTPBoundary)

    @app.middleware("http")
    async def physical_tool_request(request: Request, call_next):
        name = request.url.path.removeprefix("/tools/")
        if not request.url.path.startswith("/tools/") or name not in TOOLS:
            return await call_next(request)
        try:
            attempt_id = await run_in_threadpool(service.tracking.begin, name, request.method)
        except SQLAlchemyError:
            logger.error("physical_attempt_start_not_recorded")
            return JSONResponse(
                status_code=503,
                headers={"Cache-Control": "no-store"},
                content=ToolError(
                    code="storage_unavailable", message="Banco indisponível.", retryable=True
                ).model_dump(mode="json"),
            )
        request.state.physical_attempt_id = attempt_id
        try:
            logical_id = request.headers.get("x-tool-call-id")
            try:
                admitted = await run_in_threadpool(
                    service.admit_physical_tool_request,
                    attempt_id,
                    request.headers.get("authorization"),
                    request.headers.get("x-run-token"),
                    logical_id
                    if logical_id is not None and CALL_ID.fullmatch(logical_id)
                    else None,
                )
            except SQLAlchemyError:
                request.state.tool_error_code = "storage_unavailable"
                response = JSONResponse(
                    status_code=503,
                    headers={"Cache-Control": "no-store"},
                    content=ToolError(
                        code="storage_unavailable", message="Banco indisponível.", retryable=True
                    ).model_dump(mode="json"),
                )
            else:
                if admitted:
                    response = await call_next(request)
                else:
                    request.state.tool_error_code = "resource_limit"
                    response = JSONResponse(
                        status_code=429,
                        headers={"Cache-Control": "no-store"},
                        content=ToolError(
                            code="resource_limit",
                            message="Limite de tentativas físicas da execução atingido.",
                            retryable=False,
                        ).model_dump(mode="json"),
                    )
        except BaseException:
            await run_in_threadpool(service.tracking.complete, attempt_id, None)
            raise
        await run_in_threadpool(
            service.tracking.complete,
            attempt_id,
            response.status_code,
            getattr(request.state, "tool_error_code", None),
        )
        return response

    @app.exception_handler(ToolFailure)
    async def tool_failure(_request: Request, exc: ToolFailure):
        _request.state.tool_error_code = exc.error.code
        return JSONResponse(status_code=exc.status, content=exc.error.model_dump(mode="json"))

    @app.exception_handler(HTTPException)
    async def framework_error(request: Request, exc: HTTPException):
        code = {
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            413: "payload_too_large",
        }.get(exc.status_code, "http_error")
        request.state.tool_error_code = code
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=ToolError(code=code, message="Requisição recusada.").model_dump(mode="json"),
        )

    @app.exception_handler(ResponseValidationError)
    async def invalid_output(request: Request, _exc: ResponseValidationError):
        request.state.tool_error_code = "invalid_response"
        logger.error("http_invalid_response")
        return JSONResponse(
            status_code=500,
            content=ToolError(
                code="invalid_response", message="Resposta interna inconsistente."
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _exc: RequestValidationError):
        request.state.tool_error_code = "validation_error"
        if request.url.path.startswith("/tools/"):
            try:
                await run_in_threadpool(
                    tools.rejected,
                    request.url.path.removeprefix("/tools/"),
                    request.headers.get("authorization"),
                    lease(request),
                    call_id(request),
                    await request.body(),
                    request.state.physical_attempt_id,
                )
            except ToolFailure as exc:
                return await tool_failure(request, exc)
            except SQLAlchemyError as exc:
                return await storage_error(request, exc)
        return JSONResponse(
            status_code=422,
            content=ToolError(
                code="validation_error", message="Entrada inválida; consulte o contrato em /docs."
            ).model_dump(mode="json"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(_request: Request, _exc: SQLAlchemyError):
        _request.state.tool_error_code = "storage_unavailable"
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

    def call_id(request):
        return request.headers.get("x-tool-call-id")

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Saúde"],
        summary="Verifica API e banco",
        description="Executa SELECT 1 no banco configurado. 200 confirma essa consulta; "
        "falha SQL retorna 503 storage_unavailable. Não verifica schema completo, fila, "
        "workers, modelos ou inferência de LLM.",
        responses=errors(503),
    )
    def health() -> HealthResponse:
        with database.connect() as conn:
            conn.execute(text("SELECT 1"))
        return HealthResponse()

    @app.get(
        "/capabilities",
        response_model=CapabilitiesResponse,
        tags=["Operador"],
        summary="Configuração dos executores, presença observada e permissão de escrita",
        description="available mantém o significado legado de configuração habilitada, igual "
        "a enabled. worker_recent indica polling/heartbeat autorizado nos últimos 60 s, em "
        "escopo concedido ao operador. Não comprova inferência. Modelo remoto desconhecido "
        "é null e configuration_known é false; não são inferidos do ambiente da API.",
        responses=errors(401, 403, 503),
    )
    def capabilities(request: Request):
        return service.capabilities(actor(request))

    @app.get(
        "/processos",
        response_model=list[Process],
        tags=["Operador"],
        summary="Processos e corpus concedidos ao operador",
        description="Lista vazia autorizada retorna 200. Payload persistido deve ser válido "
        "e corresponder à identidade da linha concedida; inconsistência retorna 500 "
        "invalid_response seguro, sem lista parcial.",
        responses=errors(401, 403, 500, 503),
    )
    def list_processes(request: Request):
        return service.list_processes(actor(request))

    @app.post(
        "/conversations",
        status_code=201,
        response_model=ConversationResponse,
        tags=["Conversas"],
        summary="Cria conversa fixando processo, corpus, requisitos e executor",
        responses=errors(401, 403, 404, 409, 422, 500, 503),
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
        "existente antes da quota. Só um run ativo por conversa; outro envio recebe "
        "409 `conflict`. "
        "Compartilha com POST /runs o limite de queued por operador, padrão 20, configurável por "
        "RUN_MAX_QUEUED_PER_OPERATOR. Fila cheia retorna 429 `resource_limit`, "
        "sem gravar mensagem, run ou evento. Gravação dos três é atômica.",
        responses=errors(401, 403, 404, 409, 422, 429, 500, 503),
    )
    def send_message(conversation_id: UUID, value: MessageInput, request: Request):
        return service.create_run(actor(request), value, str(conversation_id))

    @app.post(
        "/runs",
        status_code=202,
        response_model=RunResponse,
        tags=["Execuções"],
        summary="Enfileira execução de benchmark, sem memória de chat",
        description="Limite padrão de 20 runs queued por operador, contando todos os seus "
        "processos, corpus e executores. Configurável por RUN_MAX_QUEUED_PER_OPERATOR. "
        "Replay da mesma chave/entrada precede a quota; entrada diferente mantém 409. "
        "Fila cheia retorna 429 resource_limit, sem criar run ou evento. "
        "Queued vencido é expirado antes da quota, sem exigir GET prévio.",
        responses=errors(401, 403, 404, 409, 422, 429, 500, 503),
    )
    def create_run(value: RunInput, request: Request):
        return service.create_run(actor(request), value)

    @app.post(
        "/runs/claim",
        response_model=ClaimedRun,
        tags=["Worker"],
        summary="Reserva a próxima execução do executor",
        description="Devolve `run_token`, que deve ir no cabeçalho `X-Run-Token` das tools, "
        "eventos, heartbeat e resultado. Queued vencido não é entregue; a expiração é "
        "revalidada sob a trava antes de atribuir o worker. Polling autorizado registra "
        "presença observada, inclusive quando retorna 204 sem trabalho.",
        responses={204: {"description": "Sem tarefa"}, **errors(401, 403, 422, 429, 503)},
    )
    def claim_run(value: ClaimInput, request: Request):
        result = service.claim(actor(request), value.executor, value.run_id)
        return result if result is not None else Response(status_code=204)

    @app.get(
        "/runs/{run_id}",
        response_model=RunResponse,
        tags=["Execuções"],
        summary="Snapshot consistente de status, texto parcial e cursor",
        description="Queued expira após 300 s desde created_at, configuráveis por "
        "RUN_QUEUE_TIMEOUT_SECONDS. Retorna timed_out com result.error_code queue_timeout, "
        "preservando histórico, parciais e artefatos. A regra também vale em criação e claim.",
        responses=errors(401, 403, 404, 422, 503),
    )
    def get_run(run_id: UUID, request: Request):
        return service.get_run(actor(request), str(run_id))

    @app.post(
        "/runs/{run_id}/heartbeat",
        response_model=HeartbeatResponse,
        tags=["Worker"],
        summary="Renova a reserva da execução",
        description="Renova lease e presença observada atomicamente para o worker atual "
        "autorizado, com executor compatível. Lease vencido ou execução terminal não renova.",
        responses=errors(401, 403, 409, 422, 503),
    )
    def heartbeat(run_id: UUID, request: Request):
        return service.heartbeat(actor(request), str(run_id), lease(request))

    @app.post(
        "/runs/{run_id}/events",
        response_model=EventReceipt,
        tags=["Worker"],
        summary="Publica status ou trecho de resposta; idempotente por event_id",
        description="Teto de 20.000 eventos por run, incluindo eventos do servidor e tools. "
        "A última vaga é reservada ao done. Novo evento sem capacidade retorna 429 "
        "resource_limit e encerra o run com result.error_code event_limit; consulte o snapshot. "
        "Replay idêntico de evento já aceito não consome vaga enquanto o run estiver ativo.",
        responses=errors(401, 403, 409, 422, 429, 503),
    )
    def publish_event(run_id: UUID, value: AgentEvent, request: Request):
        return service.add_event(actor(request), str(run_id), lease(request), value)

    @app.post(
        "/runs/{run_id}/result",
        response_model=RunResponse,
        tags=["Worker"],
        summary="Encerra a execução com resultado final",
        description="Com sucesso, `answer` deve coincidir com a concatenação dos `text_delta`. "
        "Benchmark bem-sucedido exige `experiment`. As chamadas declaradas devem corresponder "
        "ao histórico observado, e artefatos ao efeito da chamada. Erro no cliente pode coexistir "
        "com efeito confirmado. Duração não é comparada. Repetir o mesmo resultado é idempotente.",
        responses=errors(401, 403, 409, 422, 500, 503),
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
        "termina após o evento `done`. Até 5 conexões por operador, com leases duráveis "
        "de 30 s renovados durante o fluxo; sem capacidade retorna 429 resource_limit. "
        "Leases abandonados são recuperados após o prazo, sem reiniciar a API.",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": "text/event-stream",
                "content": {
                    "text/event-stream": {"schema": {"type": "string"}, "example": SSE_EXAMPLE}
                },
            },
            **errors(401, 403, 404, 422, 429, 503),
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
        stream_lease_id = await run_in_threadpool(service.open_stream, profile, str(run_id))

        async def generate():
            nonlocal cursor
            last_ping = time.monotonic()
            while not await request.is_disconnected():
                try:
                    current = await run_in_threadpool(actor, request)
                    await run_in_threadpool(
                        service.renew_stream, current, str(run_id), stream_lease_id
                    )
                    items, status = await run_in_threadpool(
                        service.read_events, current, str(run_id), cursor
                    )
                    encoded = [
                        (
                            item["sequence"],
                            item["kind"],
                            json.dumps(item["payload"], ensure_ascii=False),
                        )
                        for item in items
                    ]
                except Exception as exc:
                    code = (
                        exc.error.code
                        if isinstance(exc, ToolFailure)
                        else "storage_unavailable"
                        if isinstance(exc, SQLAlchemyError)
                        else "internal_error"
                    )
                    logger.warning("stream_interrupted run_id=%s code=%s", run_id, code)
                    payload = json.dumps({"message": "Fluxo interrompido.", "code": code})
                    yield f"event: stream_error\ndata: {payload}\n\n"
                    return
                for sequence, kind, data in encoded:
                    cursor = sequence
                    yield f"id: {cursor}\nevent: {kind}\ndata: {data}\n\n"
                if status in TERMINAL and len(items) < 100:
                    return
                if time.monotonic() - last_ping > 10:
                    yield ": heartbeat\n\n"
                    last_ping = time.monotonic()
                await asyncio.sleep(0.2)

        return LeasedStreamingResponse(
            generate(),
            release=lambda: service.close_stream(stream_lease_id),
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
        description="Após conferir propriedade e concessões, valida ferramenta, payload, recibo, "
        "contexto do run, identificadores e hashes. Corrupção retorna 500 `invalid_response`. "
        "A leitura não exige lease ativo nem permissão de escrita.",
        responses=errors(401, 403, 404, 422, 500, 503),
    )
    def get_artifact(artifact_id: UUID, request: Request):
        return service.get_artifact(actor(request), str(artifact_id))

    tool_errors = errors(401, 403, 404, 409, 422, 429, 500, 503)

    @app.post(
        "/tools/consultar_processo",
        response_model=ProcessResult,
        tags=["Tools"],
        summary="Metadados, inventário e cobertura da exportação",
        responses={**tool_errors, **errors(500)},
    )
    def consultar_processo(value: ToolContext, request: Request):
        return tools.call(
            "consultar_processo",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

    @app.post(
        "/tools/buscar_documentos",
        response_model=SearchResult,
        tags=["Tools"],
        summary="Busca literal de trechos com fonte",
        description="Lista vazia não prova ausência no processo original.",
        responses={**tool_errors, **errors(500)},
    )
    def buscar_documentos(value: SearchInput, request: Request):
        return tools.call(
            "buscar_documentos",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

    @app.post(
        "/tools/ler_documento",
        response_model=DocumentResult,
        tags=["Tools"],
        summary="Lê documento inteiro ou páginas específicas",
        responses=tool_errors,
    )
    def ler_documento(value: ReadInput, request: Request):
        return tools.call(
            "ler_documento",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

    @app.post(
        "/tools/consultar_requisitos",
        response_model=RequirementsResult,
        tags=["Tools"],
        summary="Checklist versionado do processo",
        responses=tool_errors,
    )
    def consultar_requisitos(value: ToolContext, request: Request):
        return tools.call(
            "consultar_requisitos",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

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
        return tools.call(
            "registrar_pendencia",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

    @app.post(
        "/tools/salvar_minuta",
        response_model=WriteReceipt,
        tags=["Tools"],
        summary="Persiste minuta fundamentada e devolve recibo",
        description="Mesma regra de idempotência de `registrar_pendencia`.",
        responses=tool_errors,
    )
    def salvar_minuta(value: WriteInput, request: Request):
        return tools.call(
            "salvar_minuta",
            actor(request),
            value,
            lease(request),
            call_id(request),
            request.state.physical_attempt_id,
        )

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
                responses = operation.setdefault("responses", {})
                for status, description in {
                    "500": ("Falha interna (internal_error) ou saída inválida (invalid_response)."),
                    "413": "Corpo acima de 1 MiB (payload_too_large).",
                    "405": "Método não permitido (method_not_allowed); preserva Allow.",
                }.items():
                    responses.setdefault(
                        status,
                        {
                            "description": description,
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ToolError"}
                                }
                            },
                        },
                    )
                if "401" in responses:
                    responses["401"].setdefault("headers", {})["WWW-Authenticate"] = {
                        "schema": {"type": "string"},
                        "description": "Bearer",
                    }
                responses["405"]["headers"] = {"Allow": {"schema": {"type": "string"}}}
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
                if path.startswith("/tools/"):
                    operation.setdefault("parameters", []).append(deepcopy(TOOL_CALL_HEADER))
                    operation["description"] = operation.get("description", "") + (
                        " Teto de 1.000 requisições físicas atribuíveis à lease por run, "
                        "incluindo erros e retries. Excesso retorna 429 resource_limit, "
                        "retryable false, antes do corpo/efeito; recusas permanecem auditadas."
                    )
        app.openapi_schema = schema
        return schema

    app.openapi = openapi
    return app

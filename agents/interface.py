"""Ponto de integração compartilhado. Nenhum executor real está implementado."""

import asyncio
import hashlib
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

import httpx
from pydantic import ValidationError

from contracts.catalog import TOOLS
from contracts.execution import AgentEvent, AgentResult, ClaimedRun
from contracts.models import (
    ReadInput,
    SearchInput,
    ToolCallRecord,
    ToolContext,
    ToolError,
)

# Erros que o modelo pode corrigir com outros argumentos; os demais encerram a chamada.
RECOVERABLE = {"validation_error", "not_found", "idempotency_conflict"}
# Tentativas por chamada lógica; só falhas transitórias são repetidas, com o mesmo corpo e ID.
ATTEMPTS = 3


class ToolCallError(httpx.HTTPStatusError):
    """Falha definitiva da tool (credencial, reserva, contexto ou servidor)."""

    def __init__(self, response: httpx.Response, error: ToolError | None):
        super().__init__(
            f"Tool recusada: HTTP {response.status_code}",
            request=response.request,
            response=response,
        )
        self.error = error


def tool_outcome(
    response: httpx.Response,
    name: str | None = None,
    expected_context: dict | None = None,
    expected_input: dict | None = None,
) -> dict:
    if response.is_success:
        name = name or response.request.url.path.rsplit("/", 1)[-1]
        try:
            result = TOOLS[name].output_model.model_validate(response.json())
            if (
                name
                in {
                    "consultar_processo",
                    "buscar_documentos",
                    "ler_documento",
                    "consultar_requisitos",
                    "registrar_pendencia",
                    "salvar_minuta",
                }
                and expected_context is not None
            ):
                expected = ToolContext.model_validate(expected_context).model_dump(mode="json")
                if result.model_dump(mode="json", include=set(expected)) != expected:
                    raise ValueError("Process response belongs to another context")
            if name == "buscar_documentos" and expected_input is not None:
                requested = SearchInput.model_validate(expected_input)
                if len(result.items) > requested.limit:
                    raise ValueError("Search response exceeded requested limit")
            if name == "ler_documento" and expected_input is not None:
                requested = ReadInput.model_validate(expected_input)
                if result.document.document_id != requested.document_id:
                    raise ValueError("Read response differs from requested document")
                if requested.pages is not None and {
                    page.number for page in result.document.pages
                } != set(requested.pages):
                    raise ValueError("Read response differs from requested pages")
            if name in {"registrar_pendencia", "salvar_minuta"} and expected_input is not None:
                requested = TOOLS[name].input_model.model_validate(expected_input)
                if result.content_sha256 != hashlib.sha256(requested.content.encode()).hexdigest():
                    raise ValueError("Write receipt differs from requested content")
            return result.model_dump(mode="json")
        except (KeyError, ValueError, ValidationError):
            # Never expose the rejected payload or retry an invalid success response.
            raise ToolCallError(response, None) from None
    try:
        error = ToolError.model_validate(response.json())
    except (ValueError, ValidationError):
        error = None
    if error is not None and error.code in RECOVERABLE:
        return {"error": error.model_dump(mode="json")}
    raise ToolCallError(response, error)


def transient(exc: Exception) -> bool:
    if isinstance(exc, ToolCallError):
        return bool(exc.error and exc.error.retryable)
    return isinstance(exc, httpx.TransportError)


def tool_payload(name: str, arguments: dict, context: dict) -> dict:
    if name not in TOOLS:
        raise ValueError("Ferramenta fora do catálogo compartilhado.")
    if any(k in arguments and arguments[k] != v for k, v in context.items()):
        raise ValueError("Contexto da tool difere da execução autenticada.")
    return {**arguments, **context}


def call_record(tool_call_id, name, started, outcome) -> ToolCallRecord:
    # Registro declarado pelo adaptador; o backend guarda o histórico de cada tentativa.
    return ToolCallRecord(
        tool_call_id=tool_call_id,
        tool=name,
        duration_ms=(time.perf_counter() - started) * 1000,
        status="ok" if outcome is not None and "error" not in outcome else "error",
        artifact_id=(outcome or {}).get("artifact_id"),
    )


class AgentAdapter(Protocol):
    def stream(
        self, execution: ClaimedRun, tools: "AsyncToolClient"
    ) -> AsyncIterator[AgentEvent | AgentResult]: ...


@dataclass(frozen=True)
class ModelConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout_seconds: float

    @classmethod
    def from_environment(cls):
        values = [os.getenv(name, "") for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")]
        if not all(values):
            raise ValueError(
                "Configure LLM_BASE_URL, LLM_MODEL e LLM_API_KEY para integração real."
            )
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
        if timeout <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS deve ser positivo.")
        return cls(*values, timeout)


class ToolClient:
    """Cliente compartilhado: seleção é do agente; execução e validação são do backend."""

    allowed = set(TOOLS)

    def __init__(self, base_url: str, token: str, context: dict, run_token: str):
        self.context = context
        self.client = httpx.Client(
            base_url=base_url,
            timeout=15,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Run-Token": run_token,
            },
        )
        self.calls: list[ToolCallRecord] = []

    def call(self, name: str, arguments: dict) -> dict:
        payload = tool_payload(name, arguments, self.context)
        tool_call_id, started, outcome = str(uuid4()), time.perf_counter(), None
        try:
            for attempt in range(ATTEMPTS):
                try:
                    response = self.client.post(
                        f"/tools/{name}", json=payload, headers={"X-Tool-Call-Id": tool_call_id}
                    )
                    outcome = tool_outcome(response, name, self.context, payload)
                    return outcome
                except (ToolCallError, httpx.TransportError) as exc:
                    if attempt == ATTEMPTS - 1 or not transient(exc):
                        raise
                time.sleep(0.3 * (attempt + 1))
        finally:
            self.calls.append(call_record(tool_call_id, name, started, outcome))

    def close(self):
        self.client.close()


class AsyncToolClient:
    def __init__(self, client: httpx.AsyncClient, execution: ClaimedRun):
        self.client = client
        self.execution = execution
        # Uma entrada por chamada lógica, para compor ExperimentRun.tool_calls.
        self.calls: list[ToolCallRecord] = []

    async def call(self, name: str, arguments: dict) -> dict:
        payload = tool_payload(name, arguments, self.execution.context)
        tool_call_id, started, outcome = str(uuid4()), time.perf_counter(), None
        headers = {"X-Run-Token": self.execution.run_token, "X-Tool-Call-Id": tool_call_id}
        try:
            for attempt in range(ATTEMPTS):
                try:
                    response = await self.client.post(
                        f"/tools/{name}", json=payload, headers=headers
                    )
                    outcome = tool_outcome(response, name, self.execution.context, payload)
                    return outcome
                except (ToolCallError, httpx.TransportError) as exc:
                    if attempt == ATTEMPTS - 1 or not transient(exc):
                        raise
                await asyncio.sleep(0.3 * (attempt + 1))
        finally:
            self.calls.append(call_record(tool_call_id, name, started, outcome))

"""Ponto de integração compartilhado. Nenhum executor real está implementado."""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx
from pydantic import ValidationError

from contracts.catalog import TOOLS
from contracts.execution import AgentEvent, AgentResult, ClaimedRun
from contracts.models import ToolError

# Erros que o modelo pode corrigir com outros argumentos; os demais encerram a chamada.
RECOVERABLE = {"validation_error", "not_found", "idempotency_conflict"}


class ToolCallError(httpx.HTTPStatusError):
    """Falha definitiva da tool (credencial, reserva, contexto ou servidor)."""

    def __init__(self, response: httpx.Response, error: ToolError | None):
        super().__init__(
            f"Tool recusada: HTTP {response.status_code}",
            request=response.request,
            response=response,
        )
        self.error = error


def tool_outcome(response: httpx.Response) -> dict:
    if response.is_success:
        return response.json()
    try:
        error = ToolError.model_validate(response.json())
    except (ValueError, ValidationError):
        error = None
    if error is not None and error.code in RECOVERABLE:
        return {"error": error.model_dump(mode="json")}
    raise ToolCallError(response, error)


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

    def call(self, name: str, arguments: dict) -> dict:
        if name not in self.allowed:
            raise ValueError("Ferramenta fora do catálogo compartilhado.")
        if any(k in arguments and arguments[k] != v for k, v in self.context.items()):
            raise ValueError("Contexto da tool difere da execução autenticada.")
        response = self.client.post(f"/tools/{name}", json={**arguments, **self.context})
        return tool_outcome(response)

    def close(self):
        self.client.close()


class AsyncToolClient:
    def __init__(self, client: httpx.AsyncClient, execution: ClaimedRun):
        self.client = client
        self.execution = execution

    async def call(self, name: str, arguments: dict) -> dict:
        if name not in ToolClient.allowed:
            raise ValueError("Ferramenta fora do catálogo compartilhado.")
        context = self.execution.context
        if any(k in arguments and arguments[k] != v for k, v in context.items()):
            raise ValueError("Contexto da tool difere da execução autenticada.")
        response = await self.client.post(
            f"/tools/{name}",
            json={**arguments, **context},
            headers={"X-Run-Token": self.execution.run_token},
        )
        return tool_outcome(response)

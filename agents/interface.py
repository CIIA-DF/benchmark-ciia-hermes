"""Interfaces compartilhadas e clientes HTTP para os executores experimentais."""

import os
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import httpx

from contracts.models import ExperimentRun, ToolContext


class AgentAdapter(Protocol):
    def run(self, task: str, context: ToolContext) -> ExperimentRun: ...


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

    allowed = {
        "consultar_processo",
        "buscar_documentos",
        "ler_documento",
    }

    def __init__(self, base_url: str, timeout_seconds: float = 15):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo.")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def call(self, name: str, arguments: dict) -> dict:
        if name not in self.allowed:
            raise ValueError("Ferramenta fora do catálogo compartilhado.")
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.post(f"/tools/{name}", json=arguments)
            response.raise_for_status()
            return response.json()


class ExperimentRunClient:
    """Grava e relê ExperimentRun pelo backend para confirmar persistência."""

    def __init__(self, base_url: str, timeout_seconds: float = 15):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds deve ser positivo.")
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def save(self, run: ExperimentRun) -> ExperimentRun:
        return self._write("post", "/experiments", run)

    def update(self, run: ExperimentRun) -> ExperimentRun:
        return self._write("put", f"/experiments/{run.run_id}", run)

    def get(self, run_id: UUID) -> ExperimentRun | None:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = client.get(f"/experiments/{run_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return ExperimentRun.model_validate(response.json())

    def _write(self, method: str, path: str, run: ExperimentRun) -> ExperimentRun:
        with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            response = getattr(client, method)(path, json=run.model_dump(mode="json"))
            response.raise_for_status()
            saved = ExperimentRun.model_validate(response.json())
            verified_response = client.get(f"/experiments/{run.run_id}")
            verified_response.raise_for_status()
            verified = ExperimentRun.model_validate(verified_response.json())
        if verified != saved or verified != run:
            raise RuntimeError("A releitura de ExperimentRun divergiu do recibo salvo.")
        return verified

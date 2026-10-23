"""Ponto de integração compartilhado pelos adaptadores de agentes."""

import os
from dataclasses import dataclass, field
from typing import Protocol

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
        "consultar_requisitos",
        "registrar_pendencia",
        "salvar_minuta",
    }

    def __init__(self, base_url: str):
        self.base_url = base_url

    def call(self, name: str, arguments: dict) -> dict:
        if name not in self.allowed:
            raise ValueError("Ferramenta fora do catálogo compartilhado.")
        with httpx.Client(base_url=self.base_url, timeout=15) as client:
            response = client.post(f"/tools/{name}", json=arguments)
            response.raise_for_status()
            return response.json()

"""Ponto de entrada do adaptador Hermes enquanto o runtime não é confirmado."""

from agents.interface import AgentAdapter
from contracts.models import ExperimentRun, ToolContext


class HermesAdapter(AgentAdapter):
    def run(self, task: str, context: ToolContext) -> ExperimentRun:
        raise NotImplementedError(
            "A integração Hermes não pode ser executada até a confirmação do runtime oficial."
        )

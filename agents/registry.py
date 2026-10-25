"""Carrega fábricas locais fornecidas pelas equipes; não implementa runtimes."""

from importlib import import_module

from agents.simulation import SimulationAdapter


def load_adapter(executor, factory=None):
    if executor == "simulation":
        if factory:
            raise ValueError("O simulador não aceita uma fábrica de agente real.")
        return SimulationAdapter()
    if executor not in {"hermes", "langgraph"} or not factory:
        raise ValueError("Executor real exige fábrica local no formato modulo:funcao.")
    module, separator, name = factory.partition(":")
    if not separator or not module or not name.isidentifier():
        raise ValueError("Fábrica inválida; use modulo:funcao.")
    try:
        adapter = getattr(import_module(module), name)()
    except Exception:
        raise ValueError("Não foi possível inicializar o adaptador configurado.") from None
    if not callable(getattr(adapter, "stream", None)):
        raise ValueError("Adaptador deve implementar AgentAdapter.stream.")
    if isinstance(adapter, SimulationAdapter):
        raise ValueError("Simulação não pode ser registrada como executor real.")
    return adapter

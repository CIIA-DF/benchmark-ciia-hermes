from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.langgraph.graph import (
    ExecutionLimits,
    build_graph,
    checkpoint_config,
    follow_up_state,
    initial_state,
    make_backend_tools,
)
from agents.langgraph.persistence import open_persistent_checkpointer
from contracts.models import ToolContext


class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"tool": name, "ok": True}


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.invocations = []

    def bind_tools(self, tools):
        self.tools = {item.name: item for item in tools}
        return self

    def invoke(self, messages):
        self.invocations.append(messages)
        return next(self.responses)


def context():
    return ToolContext(
        run_id=UUID("00000000-0000-4000-8000-000000000001"),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )


def tool_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def test_graph_executes_dynamic_model_tool_model_cycle_and_passes_task():
    client = FakeClient()
    model = FakeModel(
        [
            tool_call("consultar_processo", {}, "call-1"),
            AIMessage(content="Resposta baseada nas evidências disponíveis."),
        ]
    )
    graph = build_graph(model, client, context())

    result = graph.invoke(initial_state("Consultar o processo."))

    assert [name for name, _ in client.calls] == ["consultar_processo"]
    assert client.calls[0][1]["process_id"] == "PROC-DEMO-001"
    assert result["llm_calls"] == 2
    assert result["tool_calls"] == 1
    assert result["status"] == "completed"
    assert result["messages"][-1].content.startswith("Resposta baseada")
    assert any(
        isinstance(message, HumanMessage) and message.content == "Consultar o processo."
        for message in model.invocations[0]
    )


def test_tool_surface_only_contains_implemented_read_tools():
    names = {item.name for item in make_backend_tools(FakeClient(), context())}
    assert names == {"consultar_processo", "buscar_documentos", "ler_documento"}


def test_assisted_level_enforces_one_backend_call():
    client = FakeClient()
    model = FakeModel(
        [
            tool_call("consultar_processo", {}, "call-1"),
            tool_call("buscar_documentos", {"query": "prazo"}, "call-2"),
        ]
    )
    limits = ExecutionLimits(max_model_calls=4, max_tool_calls=8)
    graph = build_graph(model, client, context(), level="assisted", limits=limits)

    result = graph.invoke(initial_state("Consultar e pesquisar.", level="assisted", limits=limits))

    assert [name for name, _ in client.calls] == ["consultar_processo"]
    assert result["tool_calls"] == 1
    assert result["status"] == "budget_exhausted"
    assert "Limite de chamadas" in result["messages"][-1].content


def test_model_call_budget_stops_cycle_after_tool_result():
    client = FakeClient()
    model = FakeModel([tool_call("consultar_processo", {}, "call-1")])
    limits = ExecutionLimits(max_model_calls=1, max_tool_calls=3)
    graph = build_graph(model, client, context(), limits=limits)

    result = graph.invoke(initial_state("Consultar.", limits=limits))

    assert len(client.calls) == 1
    assert result["llm_calls"] == 1
    assert result["status"] == "budget_exhausted"
    assert "limite de chamadas ao modelo" in result["messages"][-1].content


def test_execution_deadline_prevents_starting_model_call():
    client = FakeClient()
    model = FakeModel([AIMessage(content="Não deve ser chamado.")])
    graph = build_graph(model, client, context())
    state = initial_state("Consulta.")
    state["deadline_at"] = 0

    result = graph.invoke(state)

    assert not model.invocations
    assert result["status"] == "deadline_exceeded"
    assert "limite de tempo" in result["messages"][-1].content


def test_resumable_level_requires_checkpoint_and_restores_same_thread():
    client = FakeClient()
    model = FakeModel([AIMessage(content="Primeira resposta."), AIMessage(content="Continuação.")])
    with pytest.raises(ValueError, match="checkpointer"):
        build_graph(model, client, context(), level="resumable")

    saver = MemorySaver()
    graph = build_graph(model, client, context(), level="resumable", checkpointer=saver)
    config = checkpoint_config(context())
    graph.invoke(initial_state("Primeira tarefa.", level="resumable"), config=config)
    result = graph.invoke(follow_up_state("Continuar análise."), config=config)

    assert result["llm_calls"] == 2
    assert result["status"] == "completed"
    assert result["messages"][-1].content == "Continuação."
    assert any(
        isinstance(message, HumanMessage) and message.content == "Primeira tarefa."
        for message in model.invocations[-1]
    )


def test_sqlite_checkpoint_survives_reopening_saver(tmp_path):
    model = FakeModel([AIMessage(content="Persistida."), AIMessage(content="Retomada após abrir.")])
    checkpoint_path = tmp_path / "langgraph.sqlite"
    config = checkpoint_config(context())

    with open_persistent_checkpointer(checkpoint_path) as saver:
        graph = build_graph(model, FakeClient(), context(), level="resumable", checkpointer=saver)
        graph.invoke(initial_state("Etapa inicial.", level="resumable"), config=config)

    with open_persistent_checkpointer(checkpoint_path) as saver:
        graph = build_graph(model, FakeClient(), context(), level="resumable", checkpointer=saver)
        result = graph.invoke(follow_up_state("Retomar tarefa."), config=config)

    assert result["llm_calls"] == 2
    assert result["messages"][-1].content == "Retomada após abrir."

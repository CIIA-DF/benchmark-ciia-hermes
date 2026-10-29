from uuid import UUID

from langchain_core.messages import AIMessage

from agents.langgraph.graph import build_graph, initial_state
from contracts.models import ToolContext


class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"tool": name, "ok": True}


class FakeModel:
    def __init__(self):
        self.invocations = 0

    def bind_tools(self, tools):
        self.tools = {item.name: item for item in tools}
        return self

    def invoke(self, messages):
        self.invocations += 1
        if self.invocations == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "consultar_processo", "args": {}, "id": "call-1", "type": "tool_call"}
                ],
            )
        return AIMessage(content="Resposta baseada nas evidências disponíveis.")


def test_graph_executes_dynamic_model_tool_model_cycle():
    context = ToolContext(
        run_id=UUID("00000000-0000-4000-8000-000000000001"),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
    client = FakeClient()
    graph = build_graph(FakeModel(), client, context)

    result = graph.invoke(initial_state("Consultar o processo."))

    assert [name for name, _ in client.calls] == ["consultar_processo"]
    assert client.calls[0][1]["process_id"] == "PROC-DEMO-001"
    assert result["llm_calls"] == 2
    assert result["tool_calls"] == 1
    assert result["messages"][-1].content.startswith("Resposta baseada")


def test_graph_contains_model_tool_and_conditional_end_nodes():
    context = ToolContext(
        run_id=UUID("00000000-0000-4000-8000-000000000001"),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
    graph = build_graph(FakeModel(), FakeClient(), context)
    node_names = set(graph.get_graph().nodes)

    assert {"model", "tools"}.issubset(node_names)

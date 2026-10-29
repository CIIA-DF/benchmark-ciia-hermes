"""Grafo inicial do executor LangGraph.

O módulo define somente a orquestração. As ferramentas continuam sendo
executadas pelo backend por meio de ``ToolClient``; o grafo não acessa banco
nem implementa regras de negócio.
"""

from typing import Literal, Protocol

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from contracts.models import ToolContext


class ToolClientLike(Protocol):
    def call(self, name: str, arguments: dict) -> dict: ...


class ChatModelLike(Protocol):
    def bind_tools(self, tools: list[BaseTool]) -> "ChatModelLike": ...

    def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...


class GraphState(MessagesState):
    """Estado observável do ciclo modelo → ferramenta → modelo."""

    task: str
    llm_calls: int
    tool_calls: int


def _context_payload(context: ToolContext) -> dict:
    return context.model_dump(mode="json")


def make_backend_tools(client: ToolClientLike, context: ToolContext) -> list[BaseTool]:
    """Cria ferramentas finas que apenas encaminham chamadas ao backend."""

    base = _context_payload(context)

    @tool
    def consultar_processo() -> dict:
        """Consulta os metadados do processo selecionado."""

        return client.call("consultar_processo", dict(base))

    @tool
    def buscar_documentos(query: str, limit: int = 5) -> dict:
        """Busca trechos literais nos documentos do processo."""

        return client.call("buscar_documentos", {**base, "query": query, "limit": limit})

    @tool
    def ler_documento(document_id: str) -> dict:
        """Lê as páginas completas de um documento."""

        return client.call("ler_documento", {**base, "document_id": document_id})

    @tool
    def consultar_requisitos() -> dict:
        """Consulta os requisitos associados à versão de requisitos."""

        return client.call("consultar_requisitos", dict(base))

    @tool
    def registrar_pendencia(
        idempotency_key: str, content: str, evidence: list[dict], evidence_note: str
    ) -> dict:
        """Registra uma pendência por meio da API autorizada."""

        return client.call(
            "registrar_pendencia",
            {
                **base,
                "idempotency_key": idempotency_key,
                "content": content,
                "evidence": evidence,
                "evidence_note": evidence_note,
            },
        )

    @tool
    def salvar_minuta(
        idempotency_key: str, content: str, evidence: list[dict], evidence_note: str
    ) -> dict:
        """Salva uma minuta por meio da API autorizada."""

        return client.call(
            "salvar_minuta",
            {
                **base,
                "idempotency_key": idempotency_key,
                "content": content,
                "evidence": evidence,
                "evidence_note": evidence_note,
            },
        )

    return [
        consultar_processo,
        buscar_documentos,
        ler_documento,
        consultar_requisitos,
        registrar_pendencia,
        salvar_minuta,
    ]


def route_after_model(state: GraphState) -> Literal["tools", "__end__"]:
    """Envia ao executor somente quando o modelo pediu ferramentas."""

    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


def build_graph(
    model: ChatModelLike,
    client: ToolClientLike,
    context: ToolContext,
    *,
    system_prompt: str = (
        "Você é um agente experimental do SEI. Use as ferramentas disponíveis "
        "quando precisar consultar evidências e não trate busca vazia como prova "
        "de ausência no processo original."
    ),
):
    """Constrói e compila o ciclo dinâmico do agente.

    O modelo decide a ferramenta e quando encerrar. A função não executa o
    grafo; o chamador fornece a tarefa no estado inicial e chama ``invoke`` ou
    ``ainvoke`` conforme o runtime escolhido.
    """

    tools = make_backend_tools(client, context)
    model_with_tools = model.bind_tools(tools)
    tool_executor = ToolNode(tools)

    def call_model(state: GraphState) -> dict:
        messages = [SystemMessage(content=system_prompt), *state["messages"]]
        response = model_with_tools.invoke(messages)
        return {
            "messages": [response],
            "llm_calls": state.get("llm_calls", 0) + 1,
        }

    def call_tools(state: GraphState) -> dict:
        result = tool_executor.invoke(state)
        last_message = state["messages"][-1]
        requested = len(last_message.tool_calls) if isinstance(last_message, AIMessage) else 0
        return {**result, "tool_calls": state.get("tool_calls", 0) + requested}

    builder = StateGraph(GraphState)
    builder.add_node("model", call_model)
    builder.add_node("tools", call_tools)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route_after_model, {"tools": "tools", END: END})
    builder.add_edge("tools", "model")
    return builder.compile()


def initial_state(task: str) -> GraphState:
    """Cria o estado inicial sem impor uma sequência de ferramentas."""

    return {"task": task, "messages": [], "llm_calls": 0, "tool_calls": 0}

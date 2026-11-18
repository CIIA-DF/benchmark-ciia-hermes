"""Orquestração LangGraph das tarefas experimentais de consulta ao SEI."""

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter, time
from typing import Any, Literal, Protocol

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from contracts.models import ToolContext

ExecutionLevel = Literal["assisted", "chained", "resumable"]


@dataclass(frozen=True)
class ExecutionLimits:
    """Limites por execução completa, incluindo continuações checkpointed."""

    max_model_calls: int = 12
    max_tool_calls: int = 8
    timeout_seconds: float = 120

    def __post_init__(self):
        if self.max_model_calls < 1 or self.max_tool_calls < 1 or self.timeout_seconds <= 0:
            raise ValueError("Limites devem ser positivos.")


DEFAULT_LIMITS: dict[ExecutionLevel, ExecutionLimits] = {
    "assisted": ExecutionLimits(max_model_calls=2, max_tool_calls=1),
    "chained": ExecutionLimits(),
    "resumable": ExecutionLimits(),
}
DEFAULT_SYSTEM_PROMPT = (
    "Você é um agente experimental para tarefas administrativas de consulta "
    "ao SEI. Você pode consultar o processo, buscar e ler documentos. Não "
    "declare que registrou pendências ou salvou minutas: essas ações não "
    "estão disponíveis. Não trate busca vazia como prova de ausência no "
    "processo original. Respeite os limites e informe quando não concluir."
)


class ToolClientLike(Protocol):
    def call(self, name: str, arguments: dict) -> dict: ...


class ChatModelLike(Protocol):
    def bind_tools(self, tools: list[BaseTool]) -> "ChatModelLike": ...

    def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...


class GraphState(MessagesState):
    """Estado de conversa, orçamento e resultado da execução."""

    task: str
    level: ExecutionLevel
    llm_calls: int
    tool_calls: int
    max_model_calls: int
    max_tool_calls: int
    deadline_at: float
    input_tokens: int
    output_tokens: int
    tool_call_records: list[dict]
    started_at: str
    elapsed_ms: float
    status: Literal["running", "completed", "budget_exhausted", "deadline_exceeded"]


def _context_payload(context: ToolContext) -> dict:
    return context.model_dump(mode="json")


def make_backend_tools(client: ToolClientLike, context: ToolContext) -> list[BaseTool]:
    """Expõe somente as ferramentas de consulta implementadas no backend."""

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

    return [consultar_processo, buscar_documentos, ler_documento]


def route_after_model(state: GraphState) -> Literal["tools", "budget_end", "__end__"]:
    """Executa chamadas válidas dentro do orçamento; encerra respostas finais."""

    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return END
    requested = len(last_message.tool_calls)
    if time() >= state["deadline_at"] or state["tool_calls"] + requested > state["max_tool_calls"]:
        return "budget_end"
    return "tools"


def build_graph(
    model: ChatModelLike,
    client: ToolClientLike,
    context: ToolContext,
    *,
    level: ExecutionLevel = "chained",
    limits: ExecutionLimits | None = None,
    checkpointer: Any | None = None,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
):
    """Compila o ciclo agente/ferramenta; nível retomável exige checkpointer."""

    if level not in DEFAULT_LIMITS:
        raise ValueError("Nível LangGraph desconhecido.")
    if level == "resumable" and checkpointer is None:
        raise ValueError("O nível resumable exige um checkpointer persistente.")

    tools = make_backend_tools(client, context)
    model_with_tools = model.bind_tools(tools)
    tool_executor = ToolNode(tools)

    def call_model(state: GraphState) -> dict:
        node_started = perf_counter()
        if time() >= state["deadline_at"]:
            return {
                "messages": [AIMessage(content="Execução encerrada pelo limite de tempo.")],
                "status": "deadline_exceeded",
            }
        if state["llm_calls"] >= state["max_model_calls"]:
            return {
                "messages": [
                    AIMessage(content="Execução encerrada pelo limite de chamadas ao modelo.")
                ],
                "status": "budget_exhausted",
            }
        response = model_with_tools.invoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )
        finished_after_deadline = time() >= state["deadline_at"]
        usage = response.usage_metadata or {}
        return {
            "messages": [response],
            "llm_calls": state["llm_calls"] + 1,
            "input_tokens": state["input_tokens"] + usage.get("input_tokens", 0),
            "output_tokens": state["output_tokens"] + usage.get("output_tokens", 0),
            "elapsed_ms": state["elapsed_ms"] + (perf_counter() - node_started) * 1000,
            "status": (
                "deadline_exceeded"
                if finished_after_deadline
                else "running"
                if response.tool_calls
                else "completed"
            ),
        }

    def call_tools(state: GraphState) -> dict:
        node_started = perf_counter()
        previous_records = getattr(client, "records", [])
        offset = len(previous_records)
        result = tool_executor.invoke(state)
        last_message = state["messages"][-1]
        requested = len(last_message.tool_calls) if isinstance(last_message, AIMessage) else 0
        new_records = getattr(client, "records", [])[offset:]
        return {
            **result,
            "tool_calls": state["tool_calls"] + requested,
            "tool_call_records": [*state["tool_call_records"], *new_records],
            "elapsed_ms": state["elapsed_ms"] + (perf_counter() - node_started) * 1000,
        }

    def budget_end(state: GraphState) -> dict:
        last_message = state["messages"][-1]
        calls = last_message.tool_calls if isinstance(last_message, AIMessage) else []
        reason = (
            "Limite de tempo atingido; as ferramentas solicitadas não foram executadas."
            if time() >= state["deadline_at"]
            else (
                "Limite de chamadas a ferramentas atingido; as ferramentas solicitadas "
                "não foram executadas."
            )
        )
        tool_messages = [ToolMessage(content=reason, tool_call_id=call["id"]) for call in calls]
        return {
            "messages": [*tool_messages, AIMessage(content=reason)],
            "status": "deadline_exceeded" if time() >= state["deadline_at"] else "budget_exhausted",
        }

    builder = StateGraph(GraphState)
    builder.add_node("model", call_model)
    builder.add_node("tools", call_tools)
    builder.add_node("budget_end", budget_end)
    builder.add_edge(START, "model")
    builder.add_conditional_edges(
        "model", route_after_model, {"tools": "tools", "budget_end": "budget_end", END: END}
    )
    builder.add_edge("tools", "model")
    builder.add_edge("budget_end", END)
    return builder.compile(checkpointer=checkpointer)


def initial_state(
    task: str,
    *,
    level: ExecutionLevel = "chained",
    limits: ExecutionLimits | None = None,
) -> GraphState:
    """Cria uma tarefa visível ao modelo e inicializa o orçamento da execução."""

    selected_limits = limits or DEFAULT_LIMITS[level]
    max_tool_calls = (
        min(selected_limits.max_tool_calls, 1)
        if level == "assisted"
        else selected_limits.max_tool_calls
    )
    return {
        "task": task,
        "level": level,
        "messages": [HumanMessage(content=task)],
        "llm_calls": 0,
        "tool_calls": 0,
        "max_model_calls": selected_limits.max_model_calls,
        "max_tool_calls": max_tool_calls,
        "deadline_at": time() + selected_limits.timeout_seconds,
        "input_tokens": 0,
        "output_tokens": 0,
        "tool_call_records": [],
        "started_at": datetime.now(UTC).isoformat(),
        "elapsed_ms": 0,
        "status": "running",
    }


def checkpoint_config(context: ToolContext) -> dict[str, dict[str, str]]:
    """Isola checkpoints da execuções diferentes usando o UUID do run."""

    return {"configurable": {"thread_id": str(context.run_id)}}


def follow_up_state(task: str) -> dict:
    """Anexa uma nova instrução sem zerar mensagens, contadores ou orçamento."""

    return {"task": task, "messages": [HumanMessage(content=task)], "status": "running"}

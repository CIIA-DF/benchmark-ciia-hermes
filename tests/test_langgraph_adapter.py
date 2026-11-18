from uuid import UUID

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.interface import ModelConfig
from agents.langgraph.adapter import LangGraphAdapter, RunMetadata
from contracts.models import ToolContext


class FakeClient:
    def call(self, name, arguments):
        return {"tool": name, "ok": True}


class FakeModel:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        return next(self.outputs)


class FakeSink:
    def __init__(self):
        self.runs = {}
        self.revisions = {}

    def save(self, run):
        self.runs[run.run_id] = run
        self.revisions[run.run_id] = [run]
        return run

    def get(self, run_id):
        return self.runs.get(run_id)

    def update(self, run):
        self.runs[run.run_id] = run
        self.revisions[run.run_id].append(run)
        return run


def build_adapter(model, sink, *, checkpointer=None):
    return LangGraphAdapter(
        model=model,
        model_config=ModelConfig(
            base_url="https://example.invalid",
            model="synthetic-test-model",
            api_key="test-secret",
            timeout_seconds=10,
        ),
        tool_client=FakeClient(),
        metadata=RunMetadata(
            task_id="DEV-001",
            split="development",
            repetition=1,
            code_commit="test-commit",
            harness_version="test-harness",
            adapter_version="test-adapter",
            endpoint_id="synthetic-endpoint",
        ),
        sink=sink,
        level="resumable" if checkpointer else "chained",
        checkpointer=checkpointer,
    )


def test_adapter_returns_response_and_experiment_record():
    sink = FakeSink()
    adapter = build_adapter(
        FakeModel(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "consultar_processo",
                            "args": {},
                            "id": "model-tool-1",
                            "type": "tool_call",
                        }
                    ],
                    usage_metadata={"input_tokens": 3, "output_tokens": 1, "total_tokens": 4},
                ),
                AIMessage(
                    content="Resposta sintética.",
                    usage_metadata={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
                ),
            ]
        ),
        sink,
    )
    context = ToolContext(
        run_id=UUID("00000000-0000-4000-8000-000000000101"),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )

    result = adapter.run_with_result("Consultar processo.", context)

    assert result.response == "Resposta sintética."
    assert result.experiment_run.executor == "langgraph"
    assert result.experiment_run.agent_declared_success
    assert result.experiment_run.verified_success is None
    assert result.experiment_run.parameters["revision"] == 1
    assert result.experiment_run.input_tokens == 8
    assert result.experiment_run.output_tokens == 3
    assert len(result.experiment_run.tool_calls) == 1
    assert result.experiment_run.tool_calls[0].tool == "consultar_processo"
    assert result.experiment_run.tool_calls[0].status == "ok"
    assert sink.get(context.run_id) == result.experiment_run


def test_adapter_resumes_and_persists_experiment_revisions():
    sink = FakeSink()
    saver = MemorySaver()
    adapter = build_adapter(
        FakeModel([AIMessage(content="Primeira resposta."), AIMessage(content="Retomada.")]),
        sink,
        checkpointer=saver,
    )
    context = ToolContext(
        run_id=UUID("00000000-0000-4000-8000-000000000102"),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )

    adapter.run_with_result("Primeira tarefa.", context)
    resumed = adapter.continue_run("Segunda etapa.", context)

    assert resumed.response == "Retomada."
    assert resumed.experiment_run.parameters["revision"] == 2
    assert sink.revisions[context.run_id][-1] == resumed.experiment_run

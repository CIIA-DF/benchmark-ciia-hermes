"""Ponte run() → stream(): adaptador síncrono falso sobre o worker e o backend reais."""

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from agents.compat import ExperimentSink, RunBridge, SyncToolClient, normalized, task_fields
from agents.worker import execute
from contracts.execution import AgentResult, ClaimedRun
from contracts.models import ExperimentRun, ToolCallRecord


def scope(corpus):
    process, _ = corpus
    return {
        k: getattr(process, k) for k in ("process_id", "corpus_version", "requirements_version")
    }


def queue_and_claim(client, corpus, kind):
    if kind == "chat":
        cid = client.post(
            "/conversations", headers=client.operator_headers, json=scope(corpus)
        ).json()["conversation_id"]
        response = client.post(
            f"/conversations/{cid}/messages",
            headers=client.operator_headers,
            json={"content": "Pergunta fictícia", "idempotency_key": str(uuid4())},
        )
    else:
        response = client.post(
            "/runs",
            headers=client.operator_headers,
            json={
                **scope(corpus),
                "task": "Tarefa fictícia",
                "task_id": "DEV-001",
                "idempotency_key": str(uuid4()),
            },
        )
    assert response.status_code in {201, 202}, response.text
    claim = client.post(
        "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
    )
    assert claim.status_code == 200, claim.text
    return ClaimedRun.model_validate(claim.json())


def report(context, task, **changes):
    values = {
        **context.model_dump(),
        "task_id": "DEV-001",
        "split": "development",
        "executor": "simulation",
        "repetition": 1,
        "code_commit": "test-only",
        "harness_version": "0.2",
        "adapter_version": "fake-run-0.1",
        "model": "not-called",
        "endpoint_id": "none",
        "prompt_sha256": hashlib.sha256(task.encode()).hexdigest(),
        "parameters": {},
        "started_at": datetime.now(UTC),
        "latency_ms": 1.0,
        "tool_calls": [],
        "agent_declared_success": True,
        "persisted_artifact_ids": [],
        "verified_success": None,
        "evaluator": None,
    }
    return ExperimentRun(**{**values, **changes})


class FakeRunAdapter:
    """Imita o formato v0.1 do Hermes: run() síncrono e resposta em final_response."""

    def __init__(self, tools: SyncToolClient, fail=False, wrong_run=False):
        self.tools = tools
        self.fail = fail
        self.wrong_run = wrong_run
        self.final_response = ""

    def run(self, task, context):
        process = self.tools.call("consultar_processo", {})
        missing = self.tools.call("ler_documento", {"document_id": "DOC-INEXISTENTE"})
        assert missing["error"]["code"] == "not_found"
        if self.fail:
            raise RuntimeError("falha simulada do adaptador")
        self.final_response = "Resposta da ponte: " + process["process"]["title"]
        changes = {"run_id": uuid4()} if self.wrong_run else {}
        return report(context, task, **changes)


def drive(client, execution, bridge):
    async def consume():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            headers=client.worker_headers,
        ) as http:
            await execute(http, execution, bridge)

    asyncio.run(consume())
    return client.get(f"/runs/{execution.run_id}", headers=client.operator_headers).json()


def test_bridge_chat_run_uses_shared_tool_client(client, corpus):
    execution = queue_and_claim(client, corpus, "chat")
    stored = drive(client, execution, RunBridge(lambda tools, _: FakeRunAdapter(tools)))
    assert stored["status"] == "succeeded", stored
    assert stored["result"]["answer"].startswith("Resposta da ponte: ")
    assert stored["result"]["experiment"] is None


def test_bridge_benchmark_reports_common_client_calls(client, corpus):
    execution = queue_and_claim(client, corpus, "benchmark")
    stored = drive(client, execution, RunBridge(lambda tools, _: FakeRunAdapter(tools)))
    assert stored["status"] == "succeeded", stored
    calls = stored["result"]["experiment"]["tool_calls"]
    # O registro vem do cliente comum (duas chamadas lógicas), não da lista vazia do adaptador.
    assert [c["tool"] for c in calls] == ["consultar_processo", "ler_documento"]
    assert [c["status"] for c in calls] == ["ok", "error"]


@pytest.mark.parametrize("options", [{"fail": True}, {"wrong_run": True}])
def test_bridge_turns_adapter_failures_into_terminal_result(client, corpus, options):
    execution = queue_and_claim(client, corpus, "benchmark")
    bridge = RunBridge(lambda tools, _: FakeRunAdapter(tools, **options))
    stored = drive(client, execution, bridge)
    assert stored["status"] == "failed", stored
    assert stored["result"]["error_code"] == "adapter_error"


def test_bridge_prefers_run_with_result(client, corpus):
    class Result:
        def __init__(self, response, experiment_run):
            self.response, self.experiment_run = response, experiment_run

    class LangGraphLike:
        def __init__(self, tools):
            self.tools = tools

        def run(self, task, context):  # pragma: no cover - não deve ser usado
            raise AssertionError("run_with_result tem precedência")

        def run_with_result(self, task, context):
            self.tools.call("consultar_requisitos", {})
            return Result("Resposta LangGraph", report(context, task))

    execution = queue_and_claim(client, corpus, "benchmark")
    stored = drive(client, execution, RunBridge(lambda tools, _: LangGraphLike(tools)))
    assert stored["status"] == "succeeded", stored
    assert stored["result"]["answer"] == "Resposta LangGraph"
    assert [c["tool"] for c in stored["result"]["experiment"]["tool_calls"]] == [
        "consultar_requisitos"
    ]


def test_bridge_emits_single_result_with_long_answer():
    class Tools:
        calls = []

    class Long:
        final_response = "x" * 9000

        def run(self, task, context):
            return report(context, task)

    execution = ClaimedRun.model_validate(
        {
            "run_id": str(uuid4()),
            "context": {
                "run_id": str(uuid4()),
                "process_id": "PROC-1",
                "corpus_version": "c1",
                "requirements_version": "r1",
            },
            "history": [],
            "task": "Tarefa",
            "task_metadata": {"task_id": "DEV-001", "split": "development", "repetition": 1},
            "kind": "chat",
            "executor": "simulation",
            "run_token": "t",
            "lease_seconds": 30,
            "heartbeat_seconds": 10,
        }
    )

    async def collect():
        return [item async for item in RunBridge(lambda *_: Long()).stream(execution, Tools())]

    items = asyncio.run(collect())
    deltas = [i.text for i in items[1:-1]]
    assert [len(d) for d in deltas] == [4000, 4000, 1000]
    assert isinstance(items[-1], AgentResult) and items[-1].answer == "".join(deltas)


def test_bridge_separates_model_timeout_from_tool_timeout():
    from agents.compat import _failure

    class Tools:
        calls = []

    client = SyncToolClient(Tools(), None)
    sink = ExperimentSink(Tools(), None)
    model = httpx.ReadTimeout("modelo")
    assert _failure(model, client, sink) == "model_timeout"
    tool = httpx.ReadTimeout("tool")
    client.errors.append(tool)
    assert _failure(tool, client, sink) == "adapter_error"
    wrapped = RuntimeError("adaptador")
    wrapped.__cause__ = tool
    assert _failure(wrapped, client, sink) == "adapter_error"
    assert _failure(ValueError("x"), client, sink) == "adapter_error"
    # Timeout em /experiments é do backend, não do modelo.
    backend = httpx.ReadTimeout("experiments")
    sink.errors.append(backend)
    assert _failure(backend, client, sink) == "adapter_error"


class LangGraphSinkLike:
    """Imita o adaptador do LangGraph (856ff06): IDs próprios de tool e gravação pelo sink."""

    def __init__(self, tools, sink, execution, revisions=1):
        self.tools, self.sink, self.revisions = tools, sink, revisions
        self.metadata = task_fields(execution)

    def run_with_result(self, task, context):
        self.tools.call("consultar_processo", {})
        own = ToolCallRecord(
            tool_call_id="tool-propria", tool="consultar_processo", duration_ms=1, status="ok"
        )
        run = report(context, task, tool_calls=[own], parameters={"level": "chained"})
        saved = self.sink.save(run)
        for revision in range(2, self.revisions + 1):
            self.tools.call("consultar_requisitos", {})
            changed = saved.model_copy(
                update={
                    "parameters": {"level": "chained", "revision": revision},
                    "latency_ms": saved.latency_ms + 1,
                }
            )
            saved = self.sink.update(changed)
        assert self.sink.get(context.run_id) == saved

        class Result:
            response, experiment_run = "Resposta LangGraph com sink", saved

        return Result()


@pytest.mark.parametrize("revisions", [1, 2])
def test_bridge_sink_records_revisions_on_server(client, corpus, revisions):
    execution = queue_and_claim(client, corpus, "benchmark")
    bridge = RunBridge(lambda tools, sink, ex: LangGraphSinkLike(tools, sink, ex, revisions))
    stored = drive(client, execution, bridge)
    assert stored["status"] == "succeeded", stored
    history = client.get(
        f"/experiments/{execution.run_id}/revisions", headers=client.operator_headers
    ).json()
    assert [item["parameters"]["revision"] for item in history] == list(range(1, revisions + 1))
    # O registro final do run é a última revisão, com os IDs do cliente comum.
    assert stored["result"]["experiment"] == history[-1]
    assert "tool-propria" not in {c["tool_call_id"] for c in history[-1]["tool_calls"]}


class SavesEarlyReturnsLater(LangGraphSinkLike):
    """Grava a revisão 1 e devolve outro relatório final sem gravar a revisão nova."""

    def run_with_result(self, task, context):
        result = super().run_with_result(task, context)
        final = result.experiment_run.model_copy(
            update={"latency_ms": result.experiment_run.latency_ms + 8000}
        )

        class Result:
            response, experiment_run = result.response, final

        return Result()


def test_bridge_fails_when_final_report_differs_from_last_revision(client, corpus):
    execution = queue_and_claim(client, corpus, "benchmark")
    bridge = RunBridge(lambda tools, sink, ex: SavesEarlyReturnsLater(tools, sink, ex))
    stored = drive(client, execution, bridge)
    # Antes, a ponte usava a revisão 1 e descartava a latência final sem erro.
    assert stored["status"] == "failed" and stored["result"]["error_code"] == "adapter_error"
    history = client.get(
        f"/experiments/{execution.run_id}/revisions", headers=client.operator_headers
    ).json()
    assert [item["parameters"]["revision"] for item in history] == [1]


def test_bridge_sink_in_chat_stays_local(client, corpus):
    execution = queue_and_claim(client, corpus, "chat")
    bridge = RunBridge(lambda tools, sink, ex: LangGraphSinkLike(tools, sink, ex))
    stored = drive(client, execution, bridge)
    assert stored["status"] == "succeeded", stored
    assert stored["result"]["experiment"] is None
    response = client.get(f"/experiments/{execution.run_id}", headers=client.operator_headers)
    assert response.status_code == 404


def test_normalized_uses_common_calls_and_artifacts():
    context = {
        "run_id": str(uuid4()),
        "process_id": "PROC-1",
        "corpus_version": "c1",
        "requirements_version": "r1",
    }

    class Context(dict):
        def model_dump(self):
            return dict(self)

    run = report(Context(context), "Tarefa")
    artifact = str(uuid4())
    calls = [
        ToolCallRecord(tool_call_id="a", tool="consultar_processo", duration_ms=1, status="ok"),
        ToolCallRecord(
            tool_call_id="b",
            tool="salvar_minuta",
            duration_ms=1,
            status="ok",
            artifact_id=artifact,
        ),
    ]
    result = normalized(run, calls)
    assert result.tool_calls == calls
    assert result.persisted_artifact_ids == [artifact]

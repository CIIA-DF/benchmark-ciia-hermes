"""P10 (item 1 da auditoria de 30/10): chamada que nunca chegou ao servidor vira contagem.

Antes, três falhas de conexão numa tool deixavam a chamada em ``tool_calls`` como ``error``; o
servidor nunca a observou, recusava o resultado com 422 e o run de benchmark terminava
``failed`` mesmo com o agente recuperado. Agora o cliente comum separa essas chamadas e declara
só a quantidade em ``parameters["unobserved_tool_calls"]``; ``tool_calls`` continua igual ao
histórico do servidor (regra do A2).
"""

import asyncio
from uuid import uuid4

import httpx
import pytest

import agents.interface as interface
from agents.compat import RunBridge
from agents.interface import AsyncToolClient, ToolClient
from agents.worker import execute
from contracts.models import UNOBSERVED_PARAMETER, ToolContext
from tests.backend.test_compat import FakeRunAdapter, queue_and_claim, report
from tests.integration.test_adapter_protocol import synthetic_execution

PROCESS = {
    "process_id": "PROC-SYNTHETIC",
    "corpus_version": "synthetic-v1",
    "requirements_version": "v1",
    "title": "Processo sintético",
    "export_completeness": "partial",
    "export_note": "Synthetic",
}


def scripted(script, context):
    seen = []

    def respond(request):
        seen.append(request.headers["X-Tool-Call-Id"])
        step = script.pop(0) if script else "ok"
        if step == "connect":
            raise httpx.ConnectError("queda sintética antes do envio", request=request)
        if step == "read":
            raise httpx.ReadTimeout("resposta perdida depois do envio", request=request)
        return httpx.Response(200, json={**context, "process": PROCESS, "inventory": []})

    return httpx.MockTransport(respond), seen


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(interface.asyncio, "sleep", instant)
    monkeypatch.setattr(interface.time, "sleep", lambda _seconds: None)


def async_calls(script):
    execution = synthetic_execution()
    transport, seen = scripted(list(script), execution.context)

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            tools = AsyncToolClient(http, execution)
            try:
                await tools.call("consultar_processo", {})
            except httpx.TransportError:
                pass
            return tools

    return asyncio.run(run()), seen


@pytest.mark.parametrize(
    ("script", "calls", "unobserved"),
    [
        (["connect", "connect", "connect"], 0, 1),
        (["read", "read", "read"], 1, 0),
        (["connect", "read", "connect"], 1, 0),
        (["connect", "ok"], 1, 0),
    ],
)
def test_async_client_separates_calls_that_never_reached_the_server(script, calls, unobserved):
    tools, seen = async_calls(script)
    assert len(seen) == min(len(script), 3)
    assert (len(tools.calls), len(tools.unobserved)) == (calls, unobserved)
    for record in tools.unobserved:
        assert record.status == "error" and record.tool_call_id == seen[0]


def test_sync_client_separates_calls_that_never_reached_the_server():
    context = {
        "run_id": str(uuid4()),
        "process_id": "PROC-SYNTHETIC",
        "corpus_version": "synthetic-v1",
        "requirements_version": "v1",
    }
    transport, seen = scripted(["connect", "connect", "connect"], context)
    client = ToolClient("http://test", "token", context, "run-token")
    client.client = httpx.Client(transport=transport, base_url="http://test")
    with pytest.raises(httpx.ConnectError):
        client.call("consultar_processo", {})
    assert len(seen) == 3 and client.calls == [] and len(client.unobserved) == 1


class LostToolTransport(httpx.AsyncBaseTransport):
    """Encaminha ao app real, mas ``ler_documento`` nunca sai do cliente."""

    def __init__(self, app):
        self.inner = httpx.ASGITransport(app=app)

    async def handle_async_request(self, request):
        if request.url.path == "/tools/ler_documento":
            raise httpx.ConnectError("queda sintética antes do envio", request=request)
        return await self.inner.handle_async_request(request)


class RecoveringAdapter(FakeRunAdapter):
    def run(self, task, context):
        process = self.tools.call("consultar_processo", {})
        with pytest.raises(httpx.ConnectError):
            self.tools.call("ler_documento", {"document_id": "DOC-QUALQUER"})
        self.final_response = "Recuperado: " + process["process"]["title"]
        return report(context, task)


def test_benchmark_run_survives_tool_that_never_reached_the_server(client, corpus):
    execution = queue_and_claim(client, corpus, "benchmark")

    async def consume():
        async with httpx.AsyncClient(
            transport=LostToolTransport(client.app),
            base_url="http://testserver",
            headers=client.worker_headers,
        ) as http:
            await execute(http, execution, RunBridge(lambda tools, _: RecoveringAdapter(tools)))

    asyncio.run(consume())
    stored = client.get(f"/runs/{execution.run_id}", headers=client.operator_headers).json()
    assert stored["status"] == "succeeded", stored
    experiment = stored["result"]["experiment"]
    assert [c["tool"] for c in experiment["tool_calls"]] == ["consultar_processo"]
    assert experiment["parameters"][UNOBSERVED_PARAMETER] == 1


@pytest.mark.parametrize("value", [-1, True, "1", 1.5])
def test_experiment_route_rejects_invalid_unobserved_count(client, corpus, value):
    execution = queue_and_claim(client, corpus, "benchmark")
    body = report(ToolContext.model_validate(execution.context), execution.task).model_dump(
        mode="json"
    )
    body["parameters"] = {UNOBSERVED_PARAMETER: value}
    headers = {**client.worker_headers, "X-Run-Token": execution.run_token}
    response = client.post("/experiments", json=body, headers=headers)
    assert response.status_code == 422, response.text


def test_revision_cannot_decrease_unobserved_count(client, corpus):
    execution = queue_and_claim(client, corpus, "benchmark")
    base = report(ToolContext.model_validate(execution.context), execution.task)
    headers = {**client.worker_headers, "X-Run-Token": execution.run_token}
    first = base.model_copy(update={"parameters": {UNOBSERVED_PARAMETER: 2}})
    assert (
        client.post("/experiments", json=first.model_dump(mode="json"), headers=headers)
    ).status_code == 200
    lower = base.model_copy(update={"parameters": {UNOBSERVED_PARAMETER: 1, "revision": 2}})
    response = client.put(
        f"/experiments/{execution.run_id}", json=lower.model_dump(mode="json"), headers=headers
    )
    assert response.status_code == 409, response.text
    higher = base.model_copy(update={"parameters": {UNOBSERVED_PARAMETER: 3, "revision": 2}})
    response = client.put(
        f"/experiments/{execution.run_id}", json=higher.model_dump(mode="json"), headers=headers
    )
    assert response.status_code == 200, response.text

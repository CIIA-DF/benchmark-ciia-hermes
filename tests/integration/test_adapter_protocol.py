"""Dublês de contrato; estes testes NÃO executam Hermes ou LangGraph reais."""

import asyncio
from uuid import uuid4

import httpx
import pytest

from agents.interface import AsyncToolClient, ToolCallError
from agents.worker import execute
from contracts.execution import AgentEvent, AgentResult, ClaimedRun
from services.backend.auth import provision


@pytest.mark.parametrize("executor", ["hermes", "langgraph"])
def test_team_adapter_protocol_uses_all_six_tools(client, corpus, engine, executor):
    scope = {
        key: getattr(corpus[0], key)
        for key in ("process_id", "corpus_version", "requirements_version")
    }
    token = uuid4().hex
    provision(
        engine,
        "probe-" + uuid4().hex,
        token,
        "worker",
        [(scope["process_id"], scope["corpus_version"])],
        can_write=True,
        executor=executor,
    )
    worker_headers = {"Authorization": "Bearer " + token}
    client.app.state.execution.enabled.add(executor)
    cid = client.post(
        "/conversations", headers=client.operator_headers, json={**scope, "executor": executor}
    ).json()["conversation_id"]
    sent = client.post(
        f"/conversations/{cid}/messages",
        headers=client.operator_headers,
        json={"content": "Prova sintética do protocolo", "idempotency_key": str(uuid4())},
    )
    run_id = sent.json()["run_id"]
    claimed = client.post(
        "/runs/claim", headers=worker_headers, json={"executor": executor, "run_id": run_id}
    )
    assert claimed.status_code == 200, claimed.text

    class ProtocolProbe:
        async def stream(self, execution, tools):
            await tools.call("consultar_processo", {})
            found = await tools.call("buscar_documentos", {"query": "material"})
            source = found["items"][0]
            await tools.call(
                "ler_documento", {"document_id": source["document_id"], "pages": [source["page"]]}
            )
            checklist = await tools.call("consultar_requisitos", {})
            data = {
                "idempotency_key": "probe-write",
                "content": "Artefato fictício de contrato",
                "evidence_note": "Prova sintética, sem avaliação semântica.",
                "evidence": [{k: source[k] for k in ("document_id", "chunk_id", "page")}],
            }
            await tools.call(
                "registrar_pendencia",
                {**data, "requirement_id": checklist["items"][0]["requirement_id"]},
            )
            receipt = await tools.call("salvar_minuta", data)
            repeated = await tools.call("salvar_minuta", data)
            assert receipt["artifact_id"] == repeated["artifact_id"]
            assert repeated["replayed"]
            # Erros corrigíveis voltam ao modelo como dados; os definitivos interrompem.
            missing = await tools.call("ler_documento", {"document_id": "INEXISTENTE"})
            assert missing["error"]["code"] == "not_found"
            changed = await tools.call("salvar_minuta", {**data, "content": "Outro conteúdo"})
            assert changed["error"]["code"] == "idempotency_conflict"
            forged = execution.model_copy(update={"run_token": "reserva-invalida"})
            with pytest.raises(ToolCallError) as refused:
                await AsyncToolClient(tools.client, forged).call("consultar_processo", {})
            assert refused.value.response.status_code == 403
            assert refused.value.error.code == "forbidden"
            yield AgentEvent(event_id=uuid4(), kind="text_delta", text="Protocolo conferido.")
            yield AgentResult(
                status="succeeded", answer="Protocolo conferido.", sources=data["evidence"]
            )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://test",
            headers=worker_headers,
        ) as transport:
            await execute(transport, ClaimedRun.model_validate(claimed.json()), ProtocolProbe())

    asyncio.run(run())
    snapshot = client.get(f"/runs/{run_id}", headers=client.operator_headers).json()
    assert snapshot["status"] == "succeeded"
    assert len(snapshot["artifacts"]) == 2
    for artifact in snapshot["artifacts"]:
        response = client.get(
            f"/artifacts/{artifact['artifact_id']}", headers=client.operator_headers
        )
        assert response.status_code == 200
        assert response.json()["payload"]["content"] == "Artefato fictício de contrato"


def test_tool_outcome_without_contract_body_is_definitive():
    from agents.interface import tool_outcome

    request = httpx.Request("POST", "http://test/tools/consultar_processo")
    with pytest.raises(ToolCallError) as refused:
        tool_outcome(httpx.Response(502, text="<html>gateway</html>", request=request))
    assert refused.value.error is None
    assert isinstance(refused.value, httpx.HTTPStatusError)
    unavailable = {
        "code": "storage_unavailable",
        "message": "Banco indisponível.",
        "retryable": True,
    }
    with pytest.raises(ToolCallError) as retry:
        tool_outcome(httpx.Response(503, json=unavailable, request=request))
    assert retry.value.error.retryable


def synthetic_execution():
    run_id = str(uuid4())
    return ClaimedRun(
        run_id=run_id,
        context={
            "run_id": run_id,
            "process_id": "PROC-SYNTHETIC",
            "corpus_version": "synthetic-v1",
            "requirements_version": "v1",
        },
        history=[{"role": "user", "content": "Pergunta sintética"}],
        task="Pergunta sintética",
        task_metadata={"task_id": "RETRY", "split": "development", "repetition": 1},
        kind="chat",
        executor="simulation",
        run_token="synthetic-lease",
        lease_seconds=60,
        heartbeat_seconds=15,
    )


@pytest.mark.parametrize(
    ("failures", "status", "attempts", "outcome"),
    [
        (["503", "transport"], 200, 3, "ok"),
        (["403"], None, 1, "raises"),
        (["503", "503", "503"], None, 3, "raises"),
    ],
)
def test_async_client_retries_only_transient_failures(
    monkeypatch, failures, status, attempts, outcome
):
    import agents.interface as interface

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(interface.asyncio, "sleep", no_wait)
    execution = synthetic_execution()
    seen = []
    script = list(failures)

    def respond(request):
        seen.append((request.headers["X-Tool-Call-Id"], request.content))
        step = script.pop(0) if script else "ok"
        if step == "transport":
            raise httpx.ConnectError("queda sintética", request=request)
        if step == "503":
            error = {"code": "storage_unavailable", "message": "Banco.", "retryable": True}
            return httpx.Response(503, json=error)
        if step == "403":
            return httpx.Response(403, json={"code": "forbidden", "message": "Recusado."})
        return httpx.Response(
            200,
            json={
                **execution.context,
                "process": {
                    "process_id": "PROC-SYNTHETIC",
                    "corpus_version": "synthetic-v1",
                    "requirements_version": "v1",
                    "title": "Processo sintético",
                    "export_completeness": "partial",
                    "export_note": "Synthetic",
                },
                "inventory": [],
            },
        )

    async def run():
        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            tools = AsyncToolClient(http, execution)
            if outcome == "ok":
                result = await tools.call("consultar_processo", {})
                assert result["process"]["title"] == "Processo sintético"
            else:
                with pytest.raises(ToolCallError):
                    await tools.call("consultar_processo", {})
            return tools.calls

    calls = asyncio.run(run())
    assert len(seen) == attempts
    assert len({call_id for call_id, _ in seen}) == 1
    assert len({body for _, body in seen}) == 1
    assert len(calls) == 1 and calls[0].tool_call_id == seen[0][0]
    assert calls[0].status == ("ok" if outcome == "ok" else "error")

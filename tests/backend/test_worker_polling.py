"""Recuperação do polling sem repetir efeitos nem depender de serviços externos."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from agents import worker


@pytest.fixture
def polling(monkeypatch):
    monkeypatch.setenv("BACKEND_WORKER_TOKEN", "synthetic-worker-token-for-polling-tests")
    real_client = httpx.AsyncClient
    sleep = AsyncMock()
    execute = AsyncMock()
    monkeypatch.setattr(worker.asyncio, "sleep", sleep)
    monkeypatch.setattr(worker, "execute", execute)

    def configure(handler):
        monkeypatch.setattr(
            worker.httpx,
            "AsyncClient",
            lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
        )
        return sleep, execute

    return configure


@pytest.mark.parametrize("failures", [1, 3])
def test_worker_recovers_after_claim_503(polling, failures):
    run_id = str(uuid4())
    claimed = {
        "run_id": run_id,
        "context": {"run_id": run_id},
        "history": [{"role": "user", "content": "Pergunta sintética"}],
        "task": "Pergunta sintética",
        "task_metadata": {"task_id": "POLLING"},
        "kind": "chat",
        "executor": "simulation",
        "run_token": "synthetic-lease",
        "lease_seconds": 60,
        "heartbeat_seconds": 15,
    }
    calls = 0

    def respond(request):
        nonlocal calls
        assert request.url.path == "/runs/claim"
        calls += 1
        if calls <= failures:
            return httpx.Response(503, json={"code": "storage_unavailable", "retryable": True})
        if calls == failures + 1:
            return httpx.Response(200, json=claimed)
        # Interrompe o worker contínuo após comprovar que processou a reserva.
        return httpx.Response(401)

    sleep, execute = polling(respond)
    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(worker.work(object(), "simulation"))
    assert error.value.response.status_code == 401
    assert calls == failures + 2
    assert [call.args[0] for call in sleep.await_args_list] == [2] * failures + [0.4]
    execute.assert_awaited_once()
    assert str(execute.await_args.args[1].run_id) == run_id


@pytest.mark.parametrize("status", [401, 403])
def test_worker_does_not_retry_definitive_claim_errors(polling, status):
    calls = 0

    def respond(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(status)

    sleep, execute = polling(respond)
    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(worker.work(object(), "simulation"))
    assert error.value.response.status_code == status
    assert calls == 1
    sleep.assert_not_awaited()
    execute.assert_not_awaited()


def test_once_worker_reports_503_without_retry(polling):
    calls = 0

    def respond(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    sleep, execute = polling(respond)
    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(worker.work(object(), "simulation", once=True))
    assert error.value.response.status_code == 503
    assert calls == 1
    sleep.assert_not_awaited()
    execute.assert_not_awaited()


def test_heartbeat_never_follows_final_result():
    # Confirmação lenta do resultado cruza o timer do heartbeat; a reserva já foi encerrada.
    from contracts.execution import AgentResult, ClaimedRun

    run_id = str(uuid4())
    execution = ClaimedRun(
        run_id=run_id,
        context={"run_id": run_id},
        history=[{"role": "user", "content": "Pergunta sintética"}],
        task="Pergunta sintética",
        task_metadata={"task_id": "HEARTBEAT"},
        kind="chat",
        executor="simulation",
        run_token="synthetic-lease",
        lease_seconds=60,
        heartbeat_seconds=1,
    )
    log = []

    async def respond(request):
        name = request.url.path.rsplit("/", 1)[-1]
        log.append(name)
        if name == "result":
            await asyncio.sleep(1)
            return httpx.Response(200, json={})
        if name == "heartbeat" and "result" in log:
            return httpx.Response(409, json={"code": "conflict", "message": "Execução encerrada."})
        return httpx.Response(200, json={"status": "running"})

    class SlowAdapter:
        async def stream(self, execution, tools):
            await asyncio.sleep(0.5)
            yield AgentResult(status="succeeded", answer="Resposta sintética")

    async def run():
        transport = httpx.MockTransport(respond)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await worker.execute(client, execution, SlowAdapter())

    asyncio.run(run())
    assert log == ["result"]

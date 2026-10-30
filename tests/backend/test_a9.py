"""A9: durable SSE admission, recovery, reauthorization and response cleanup."""

import asyncio
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import delete, inspect, select
from starlette.requests import ClientDisconnect

from services.backend.auth import authenticate
from services.backend.errors import ToolFailure
from services.backend.execution import SSE_LEASE_SECONDS
from services.backend.migrate import migrate
from services.backend.schema import permissions, runs, stream_leases
from services.backend.streaming import LeasedStreamingResponse
from tests.backend import test_a5
from tests.backend.test_a7 import start
from tests.backend.test_execution import finish


@pytest.fixture
def clock(monkeypatch):
    return test_a5.clock.__wrapped__(monkeypatch)


def leases(engine):
    with engine.connect() as conn:
        return [dict(item) for item in conn.execute(select(stream_leases)).mappings()]


def operator(client, engine):
    return authenticate(engine, client.operator_headers["Authorization"])


def test_operator_quota_is_shared_and_http_rejects_before_headers(client, corpus, engine):
    run, _ = start(client, corpus)
    service = client.app.state.execution
    profile = operator(client, engine)
    identities = [service.open_stream(profile, run["run_id"]) for _ in range(5)]
    response = client.get(f"/runs/{run['run_id']}/events", headers=client.operator_headers)
    assert response.status_code == 429 and response.json()["code"] == "resource_limit"
    assert response.json()["retryable"] is True
    assert response.headers["cache-control"] == "no-store"
    assert "text/event-stream" not in response.headers["content-type"]
    assert len(leases(engine)) == 5
    assert (
        client.get(
            f"/runs/{run['run_id']}/events?after=-1", headers=client.operator_headers
        ).status_code
        == 422
    )
    service.close_stream(identities[0])
    replacement = service.open_stream(profile, run["run_id"])
    assert replacement not in identities and len(leases(engine)) == 5


def test_abandoned_lease_recovery_and_expired_stream_cannot_resurrect(
    client, corpus, engine, clock
):
    run, _ = start(client, corpus)
    service = client.app.state.execution
    actor = operator(client, engine)
    old = [service.open_stream(actor, run["run_id"]) for _ in range(5)]
    clock.now += SSE_LEASE_SECONDS / 2
    service.renew_stream(actor, run["run_id"], old[0])
    clock.now += SSE_LEASE_SECONDS / 2
    fresh = [service.open_stream(actor, run["run_id"]) for _ in range(4)]
    assert len(leases(engine)) == 5
    with pytest.raises(ToolFailure) as refused:
        service.renew_stream(actor, run["run_id"], old[1])
    assert refused.value.status == 409
    assert {item["lease_id"] for item in leases(engine)} == {old[0], *fresh}
    service.close_stream(old[1])  # Late cleanup cannot remove a replacement lease.
    assert len(leases(engine)) == 5


def test_separate_processes_cannot_overbook_last_slot(client, corpus, engine):
    run, _ = start(client, corpus)
    service = client.app.state.execution
    profile = operator(client, engine)
    for _ in range(4):
        service.open_stream(profile, run["run_id"])
    code = """
import json, os, sys
from services.backend.auth import authenticate
from services.backend.errors import ToolFailure
from services.backend.execution import ExecutionService
from services.backend.storage import make_engine
engine = make_engine(sys.argv[1])
try:
    actor = authenticate(engine, os.environ["SYNTHETIC_SSE_AUTH"])
    ExecutionService(engine).open_stream(actor, sys.argv[2])
    print(json.dumps({"status": 200}))
except ToolFailure as exc:
    print(json.dumps({"status": exc.status}))
finally:
    engine.dispose()
"""
    env = {**os.environ, "SYNTHETIC_SSE_AUTH": client.operator_headers["Authorization"]}

    def open_one(_):
        completed = subprocess.run(
            [sys.executable, "-c", code, str(engine.url), run["run_id"]],
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        )
        return json.loads(completed.stdout)["status"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(open_one, range(2))) == [200, 429]
    assert len(leases(engine)) == 5


@pytest.mark.parametrize("mode", ["finish", "cancel", "revoke"])
def test_live_http_stream_releases_on_completion_disconnect_or_revocation(
    client, corpus, engine, mode
):
    run, headers = start(client, corpus)
    rid = run["run_id"]

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://test"
        ) as http:
            task = asyncio.create_task(
                http.get(f"/runs/{rid}/events", headers=client.operator_headers)
            )
            for _ in range(200):
                if leases(engine):
                    break
                await asyncio.sleep(0.01)
            assert len(leases(engine)) == 1
            if mode == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                if mode == "finish":
                    assert finish(client, run, headers).status_code == 200
                else:
                    profile = operator(client, engine)
                    with engine.begin() as conn:
                        conn.execute(
                            delete(permissions).where(
                                permissions.c.principal_id == profile["principal_id"],
                            )
                        )
                response = await asyncio.wait_for(task, timeout=10)
                assert response.status_code == 200
                if mode == "finish":
                    assert response.text.count("event: done") == 1
                else:
                    assert response.text.count("event: stream_error") == 1
                    assert '"code": "forbidden"' in response.text
        assert leases(engine) == []

    asyncio.run(exercise())


def test_send_failure_before_body_releases_even_without_iterating(client, corpus, engine):
    run, _ = start(client, corpus)
    service = client.app.state.execution
    identity = service.open_stream(operator(client, engine), run["run_id"])

    async def content():
        pytest.fail("Body must not be iterated after header send failure")
        yield "unreachable"

    async def exercise():
        async def receive():
            return {"type": "http.disconnect"}

        async def send(_):
            raise OSError("Synthetic closed socket")

        response = LeasedStreamingResponse(
            content(), release=lambda: service.close_stream(identity)
        )
        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    asyncio.run(exercise())
    assert leases(engine) == []


def test_stream_migration_preserves_run_and_does_not_infer_sessions(client, corpus, engine):
    run, _ = start(client, corpus)
    migrate(engine, "0007", downgrade=True)
    assert "stream_leases" not in inspect(engine).get_table_names()
    migrate(engine)
    assert leases(engine) == []
    with engine.connect() as conn:
        assert conn.execute(
            select(runs.c.run_id).where(runs.c.run_id == run["run_id"])
        ).scalar_one()

"""Integrated regressions for durable logical calls and transport contracts."""

from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import func, select

from agents.interface import ToolCallError, tool_outcome
from services.backend.schema import artifacts, logical_tool_calls
from tests.backend.test_tool_calls import history, write_body


def test_changed_input_cannot_reuse_id_and_retry_recovers_receipt(client, corpus, context, engine):
    client.app.state.execution.max_tool_calls = 1
    headers = {"X-Tool-Call-Id": "same"}
    body = write_body(context, corpus)
    first = client.post("/tools/salvar_minuta", headers=headers, json=body)
    assert first.status_code == 200
    changed = client.post(
        "/tools/salvar_minuta",
        headers=headers,
        json=write_body(context, corpus, key="other", content="Other"),
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    replay = client.post("/tools/salvar_minuta", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["artifact_id"] == first.json()["artifact_id"]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )


def test_failed_effect_keeps_identity_and_budget(client, corpus, context, engine):
    client.app.state.execution.max_tool_calls = 1
    body = write_body(context, corpus)
    body["evidence"] = [{"document_id": "missing", "chunk_id": "missing", "page": 1}]
    assert (
        client.post(
            "/tools/salvar_minuta", headers={"X-Tool-Call-Id": "failed"}, json=body
        ).status_code
        == 422
    )
    other = client.post(
        "/tools/consultar_processo", headers={"X-Tool-Call-Id": "failed"}, json=context
    )
    assert other.json()["code"] == "idempotency_conflict"
    new = client.post("/tools/consultar_processo", headers={"X-Tool-Call-Id": "new"}, json=context)
    assert new.json()["code"] == "budget_exceeded"
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()["tool"]
            == "salvar_minuta"
        )
    assert len(history(client, engine, context["run_id"])) == 3


def test_concurrent_different_effects_same_id(client, corpus, context, engine):
    def write(index):
        return client.post(
            "/tools/salvar_minuta",
            headers={"X-Tool-Call-Id": "concurrent"},
            json=write_body(context, corpus, key=f"key-{index}", content=f"Synthetic {index}"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(history(client, engine, context["run_id"])) == 2


def test_rejected_input_binds_id(client, context):
    headers = {"X-Tool-Call-Id": "invalid"}
    assert client.post("/tools/buscar_documentos", headers=headers, json=context).status_code == 422
    response = client.post(
        "/tools/buscar_documentos", headers=headers, json={**context, "query": "fixed"}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_conflict"


@pytest.mark.parametrize(
    "name",
    [
        "consultar_processo",
        "buscar_documentos",
        "ler_documento",
        "consultar_requisitos",
        "registrar_pendencia",
        "salvar_minuta",
    ],
)
def test_malformed_success_is_definitive_without_echo(name):
    response = httpx.Response(
        200,
        json={"secret": "synthetic-rejected-content"},
        request=httpx.Request("POST", f"http://test/tools/{name}"),
    )
    with pytest.raises(ToolCallError) as error:
        tool_outcome(response, name)
    assert error.value.error is None
    assert "synthetic-rejected-content" not in str(error.value)


def test_invalid_reuse_and_budget_have_safe_http_envelope(client, context):
    client.app.state.execution.max_tool_calls = 1
    headers = {"X-Tool-Call-Id": "bad"}
    assert client.post("/tools/buscar_documentos", headers=headers, json=context).status_code == 422
    changed = client.post(
        "/tools/buscar_documentos", headers=headers, json={**context, "query": 123}
    )
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    denied = client.post(
        "/tools/buscar_documentos", headers={"X-Tool-Call-Id": "new"}, json=context
    )
    assert denied.status_code == 409
    assert denied.json()["code"] == "budget_exceeded"


def test_reservation_survives_failure_before_effect(client, context, monkeypatch, engine):
    from sqlalchemy.exc import SQLAlchemyError

    from services.backend.tools import ToolService

    original = ToolService.process

    def broken(*args):
        raise SQLAlchemyError("synthetic-private-detail")

    monkeypatch.setattr(ToolService, "process", broken)
    headers = {"X-Tool-Call-Id": "reserved"}
    response = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert response.status_code == 503 and "synthetic-private-detail" not in response.text
    monkeypatch.setattr(ToolService, "process", original)
    different = client.post("/tools/consultar_requisitos", headers=headers, json=context)
    assert different.json()["code"] == "idempotency_conflict"
    assert (
        client.post("/tools/consultar_processo", headers=headers, json=context).status_code == 200
    )


def test_0005_backfills_first_identity_without_rewriting_attempts(client, context, engine):
    from services.backend.migrate import migrate

    headers = {"X-Tool-Call-Id": "historical"}
    assert (
        client.post("/tools/consultar_processo", headers=headers, json=context).status_code == 200
    )
    before = history(client, engine, context["run_id"])
    migrate(engine, "0004", downgrade=True)
    migrate(engine)
    assert history(client, engine, context["run_id"]) == before
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert row["args_sha256"] == before[0]["args_sha256"]
    denied = client.post("/tools/consultar_requisitos", headers=headers, json=context)
    assert denied.json()["code"] == "idempotency_conflict"


@pytest.mark.parametrize("tool", ["salvar_minuta", "registrar_pendencia"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_lost_response_after_commit_retries_without_duplicate(
    client, corpus, context, engine, asynchronous, tool
):
    import asyncio
    import json

    from agents.interface import AsyncToolClient, ToolClient
    from contracts.execution import ClaimedRun

    seen = []

    def respond(request):
        seen.append((request.headers["X-Tool-Call-Id"], request.content))
        response = client.post(
            request.url.path, headers=dict(request.headers), json=json.loads(request.content)
        )
        assert response.status_code == 200
        if len(seen) == 1:
            raise httpx.ReadTimeout("synthetic lost receipt after commit", request=request)
        return httpx.Response(response.status_code, json=response.json())

    body = write_body(context, corpus)
    if tool == "registrar_pendencia":
        body["requirement_id"] = "REQ-DEMO-001"
    arguments = {k: v for k, v in body.items() if k not in context}
    token = client.worker_headers["Authorization"].removeprefix("Bearer ")
    if asynchronous:
        execution = ClaimedRun(
            run_id=context["run_id"],
            context=context,
            history=[],
            task="Synthetic",
            task_metadata={"task_id": "T0", "split": "development", "repetition": 1},
            kind="benchmark",
            executor="simulation",
            run_token=client.headers["X-Run-Token"],
            lease_seconds=60,
            heartbeat_seconds=15,
        )

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(respond),
                base_url="http://test",
                headers=client.worker_headers,
            ) as http:
                tools = AsyncToolClient(http, execution)
                result = await tools.call(tool, arguments)
                return result, tools.calls

        result, records = asyncio.run(run())
    else:
        tools = ToolClient("http://test", token, context, client.headers["X-Run-Token"])
        tools.client.close()
        tools.client = httpx.Client(
            transport=httpx.MockTransport(respond),
            base_url="http://test",
            headers={**client.worker_headers, "X-Run-Token": client.headers["X-Run-Token"]},
        )
        try:
            result = tools.call(tool, arguments)
            records = tools.calls
        finally:
            tools.close()
    assert result["replayed"] and len(records) == 1
    assert len(seen) == 2 and seen[0] == seen[1]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    assert [row["replayed"] for row in history(client, engine, context["run_id"])] == [False, True]

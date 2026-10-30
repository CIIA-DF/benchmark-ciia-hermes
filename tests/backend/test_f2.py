"""F2: reject NUL before SQL while preserving physical attribution and budget."""

import asyncio
import hashlib
import json
import re

import httpx
import pytest
from sqlalchemy import event, select

from agents.interface import AsyncToolClient, ToolClient
from contracts.catalog import tool_catalog
from contracts.execution import ClaimedRun
from services.backend.schema import logical_tool_calls
from tests.backend.test_tool_calls import history


def search(client, context, query, call_id="nul-search"):
    return client.post(
        "/tools/buscar_documentos",
        headers={"X-Tool-Call-Id": call_id},
        json={**context, "query": query},
    )


@pytest.mark.parametrize("query", ["\x00", "\x00material", "material\x00", "mate\x00rial"])
def test_nul_is_safe_422_before_search_sql_and_is_attributed(client, context, engine, query):
    def no_search(conn, cursor, statement, params, exec_context, many):
        assert "FROM chunks" not in statement, "NUL must not reach search SQL"

    event.listen(engine, "before_cursor_execute", no_search)
    try:
        response = search(client, context, query)
    finally:
        event.remove(engine, "before_cursor_execute", no_search)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert not response.json()["retryable"]
    assert "material" not in response.text and "\\u0000" not in response.text
    with engine.connect() as conn:
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
        physical = client.app.state.execution.tracking.history(conn, context["run_id"])
    assert logical["tool"] == "buscar_documentos" and logical["tool_call_id"] == "nul-search"
    assert logical["args_sha256"] == hashlib.sha256(response.request.content).hexdigest()
    assert len(physical) == 1 and physical[0]["args_sha256"] == logical["args_sha256"]
    assert physical[0]["http_status"] == 422 and physical[0]["code"] == "validation_error"
    assert physical[0]["client_received"] is None
    assert [p["phase"] for p in physical[0]["phases"]] == ["started", "failed"]
    assert history(client, engine, context["run_id"])[0]["code"] == "validation_error"


def test_rejected_nul_keeps_binding_and_budget_and_repeat_is_another_physical_attempt(
    client, context, engine
):
    client.app.state.execution.max_tool_calls = 1
    assert search(client, context, "mate\x00rial").status_code == 422
    same = search(client, context, "mate\x00rial")
    assert same.status_code == 422
    changed = search(client, context, "material")
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    new = search(client, context, "material", "new-search")
    assert new.status_code == 409 and new.json()["code"] == "budget_exceeded"
    with engine.connect() as conn:
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .all()
        )
        physical = client.app.state.execution.tracking.history(conn, context["run_id"])
    assert len(logical) == 1 and len(physical) == 4
    assert len({r["attempt_id"] for r in physical}) == 4
    assert sorted(r["http_status"] for r in physical) == [409, 409, 422, 422]
    assert all(len(r["phases"]) == 2 for r in physical)


def test_nul_without_valid_lease_is_not_attributed_to_body_run(client, context, engine):
    response = client.post(
        "/tools/buscar_documentos",
        headers={"X-Run-Token": "invalid-lease"},
        json={**context, "query": "material\x00"},
    )
    assert response.status_code == 422
    with engine.connect() as conn:
        assert client.app.state.execution.tracking.history(conn, context["run_id"]) == []
        assert (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            ).first()
            is None
        )
    assert history(client, engine, context["run_id"]) == []


def test_openapi_and_tool_catalog_expose_nul_constraint_without_rejecting_literal_escape(
    client, context
):
    schema = client.get("/openapi.json").json()["components"]["schemas"]["SearchInput"][
        "properties"
    ]["query"]
    tool = next(v for v in tool_catalog() if v["name"] == "buscar_documentos")
    assert tool["parameters"]["properties"]["query"]["pattern"] == schema["pattern"]
    assert re.search(schema["pattern"], "material\x00") is None
    assert re.search(schema["pattern"], r"\u0000") is not None
    response = search(client, context, r"\u0000", "literal-escape")
    assert response.status_code == 200 and response.json()["items"] == []


@pytest.mark.parametrize("asynchronous", [False, True])
def test_both_clients_receive_recoverable_validation_without_retry_or_search(
    client, context, engine, asynchronous
):
    seen = []

    def respond(request):
        seen.append(request.content)
        response = client.post(
            request.url.path, headers=dict(request.headers), json=json.loads(request.content)
        )
        assert response.status_code == 422
        return httpx.Response(422, json=response.json())

    if asynchronous:
        execution = ClaimedRun(
            run_id=context["run_id"],
            context=context,
            history=[],
            task="Synthetic",
            task_metadata={"task_id": "F2", "split": "development", "repetition": 1},
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
                result = await tools.call("buscar_documentos", {"query": "material\x00"})
                return result, tools.calls

        result, calls = asyncio.run(run())
    else:
        tools = ToolClient("http://test", "unused", context, client.headers["X-Run-Token"])
        tools.client.close()
        tools.client = httpx.Client(
            transport=httpx.MockTransport(respond),
            base_url="http://test",
            headers={**client.worker_headers, "X-Run-Token": client.headers["X-Run-Token"]},
        )
        try:
            result = tools.call("buscar_documentos", {"query": "material\x00"})
            calls = tools.calls
        finally:
            tools.close()
    assert result["error"]["code"] == "validation_error" and not result["error"]["retryable"]
    assert len(seen) == len(calls) == 1 and calls[0].status == "error"
    with engine.connect() as conn:
        physical = client.app.state.execution.tracking.history(conn, context["run_id"])
    assert len(physical) == 1 and physical[0]["http_status"] == 422

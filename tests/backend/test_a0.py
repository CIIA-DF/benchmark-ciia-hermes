"""A0: HTTP boundary, real chunk messages, safe errors and SSE lifecycle."""

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from contracts.models import ToolError
from services.backend.http_boundary import MAX_BODY_BYTES, HTTPBoundary
from services.backend.schema import physical_tool_attempts


def assert_error(response, status, code):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert ToolError.model_validate(response.json()).code == code
    assert "PRIVATE" not in response.text


def test_framework_errors_preserve_status_headers_and_hide_detail(client):
    @client.app.get("/a0/framework")
    def framework():
        raise HTTPException(401, "PRIVATE", headers={"X-Probe": "preserved"})

    assert_error(client.get("/a0/absent"), 404, "not_found")
    wrong_method = client.post("/capabilities")
    assert_error(wrong_method, 405, "method_not_allowed")
    assert "GET" in wrong_method.headers["allow"]
    challenge = client.get("/a0/framework")
    assert_error(challenge, 401, "unauthorized")
    assert challenge.headers["www-authenticate"] == "Bearer"
    assert challenge.headers["x-probe"] == "preserved"


def test_auth_domain_input_output_and_internal_errors_are_distinct(client, monkeypatch, caplog):
    bad = client.get("/capabilities", headers={"Authorization": "Bearer PRIVATE"})
    assert_error(bad, 401, "unauthorized")
    assert bad.headers["www-authenticate"] == "Bearer"
    assert_error(client.get("/capabilities"), 403, "forbidden")
    assert_error(client.get("/runs/PRIVATE"), 422, "validation_error")
    ok = client.get("/capabilities", headers=client.operator_headers)
    assert ok.status_code == 200 and ok.headers["cache-control"] == "no-store"

    monkeypatch.setattr(
        client.app.state.execution, "list_processes", lambda *_: [{"title": "PRIVATE"}]
    )
    assert_error(client.get("/processos", headers=client.operator_headers), 500, "invalid_response")

    @client.app.get("/a0/internal")
    def internal():
        raise ValueError("PRIVATE")

    assert_error(client.get("/a0/internal"), 500, "internal_error")
    assert "PRIVATE" not in caplog.text


@pytest.mark.parametrize(
    "chunks,declared,status",
    [
        ([b"x" * MAX_BODY_BYTES], None, 200),
        ([b"x" * MAX_BODY_BYTES, b"x"], None, 413),
        ([b"x" * 600_000, b"x" * 600_000], b"1", 413),
        ([], str(MAX_BODY_BYTES + 1).encode(), 413),
        ([], b"9" * 5000, 413),
    ],
)
def test_actual_asgi_chunk_limit(chunks, declared, status):
    seen = []

    async def endpoint(scope, receive, send):
        body = await receive()
        seen.append(body["body"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def exercise():
        messages = [
            {"type": "http.request", "body": chunk, "more_body": i < len(chunks) - 1}
            for i, chunk in enumerate(chunks)
        ]

        async def receive():
            assert messages, "Declared oversize must not consume the body"
            return messages.pop(0)

        sent = []

        async def send(message):
            sent.append(message)

        headers = [] if declared is None else [(b"content-length", declared)]
        await HTTPBoundary(endpoint)(
            {"type": "http", "path": "/a0/body", "headers": headers}, receive, send
        )
        return sent

    sent = asyncio.run(exercise())
    assert sent[0]["status"] == status
    assert (b"cache-control", b"no-store") in sent[0]["headers"]
    if status == 413:
        assert not seen
        assert ToolError.model_validate_json(sent[1]["body"]).code == "payload_too_large"
    else:
        assert seen == [b"x" * MAX_BODY_BYTES]


def test_tool_oversize_is_recorded_without_logical_binding(client, engine):
    response = client.post("/tools/consultar_processo", content=b"x" * (MAX_BODY_BYTES + 1))
    assert_error(response, 413, "payload_too_large")
    with engine.connect() as conn:
        row = conn.execute(select(physical_tool_attempts)).mappings().one()
    assert row["http_status"] == 413 and row["code"] == "payload_too_large"
    assert row["run_id"] is None and row["tool_call_id"] is None


@pytest.mark.parametrize(
    "failure,code",
    [
        (SQLAlchemyError("PRIVATE"), "storage_unavailable"),
        (ValueError("PRIVATE"), "internal_error"),
    ],
)
def test_sse_before_and_after_headers(client, context, monkeypatch, failure, code, caplog):
    service = client.app.state.execution
    url = f"/runs/{context['run_id']}/events"
    original = service.get_run

    def fail(*_):
        raise failure

    monkeypatch.setattr(service, "get_run", fail)
    assert_error(
        client.get(url, headers=client.operator_headers),
        503 if code == "storage_unavailable" else 500,
        code,
    )
    monkeypatch.setattr(service, "get_run", original)
    monkeypatch.setattr(service, "read_events", fail)
    response = client.get(url, headers=client.operator_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.text.count("event: stream_error") == 1
    assert json.loads(response.text.split("data: ")[1])["code"] == code
    assert "PRIVATE" not in response.text + caplog.text


def test_sse_domain_failure_after_open_and_missing_run_before_open(client, context, monkeypatch):
    from services.backend.errors import fail

    missing = client.get(f"/runs/{uuid4()}/events", headers=client.operator_headers)
    assert_error(missing, 404, "not_found")

    def revoked(*_):
        fail(403, "forbidden", "PRIVATE")

    monkeypatch.setattr(client.app.state.execution, "read_events", revoked)
    response = client.get(f"/runs/{context['run_id']}/events", headers=client.operator_headers)
    assert response.status_code == 200 and '"code": "forbidden"' in response.text
    assert "PRIVATE" not in response.text


def test_success_stream_is_not_buffered_and_has_no_second_response():
    async def exercise():
        emitted = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            emitted.append(message)

        async def stream(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send(
                {"type": "http.response.body", "body": b"data: first\n\n", "more_body": True}
            )
            assert len(emitted) == 2
            raise RuntimeError("PRIVATE")

        with pytest.raises(RuntimeError):
            await HTTPBoundary(stream)(
                {"type": "http", "path": "/stream", "headers": []}, receive, send
            )
        assert sum(m["type"] == "http.response.start" for m in emitted) == 1

    asyncio.run(exercise())

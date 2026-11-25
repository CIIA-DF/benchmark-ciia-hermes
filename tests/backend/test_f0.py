"""F0: physical requests, durable effect phases and additive legacy migration."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from services.backend.migrate import migrate
from services.backend.schema import artifacts, physical_tool_attempts, physical_tool_phases
from tests.backend.test_tool_calls import history, write_body


def physical(client, engine, context):
    with engine.connect() as conn:
        return client.app.state.execution.tracking.history(conn, context["run_id"])


def send(client, tool, body, call_id="logical"):
    return client.post(f"/tools/{tool}", headers={"X-Tool-Call-Id": call_id}, json=body)


@pytest.mark.parametrize("tool", ["registrar_pendencia", "salvar_minuta"])
def test_postcommit_retry_is_two_physical_attempts_and_one_artifact(
    client, engine, context, corpus, tool
):
    body = write_body(context, corpus)
    if tool == "registrar_pendencia":
        body["requirement_id"] = "REQ-DEMO-001"
    reads = []

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM artifacts" in statement:
            reads.append(statement)
            if len(reads) == 3:
                raise SQLAlchemyError("SYNTHETIC-PRIVATE-POSTCOMMIT")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        first = send(client, tool, body)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert first.status_code == 503 and "SYNTHETIC-PRIVATE" not in first.text
    second = send(client, tool, body)
    assert second.status_code == 200 and second.json()["replayed"]
    rows = physical(client, engine, context)
    assert len(rows) == 2 and len({r["attempt_id"] for r in rows}) == 2
    assert [r["http_status"] for r in rows] == [503, 200]
    assert [p["phase"] for p in rows[0]["phases"]] == ["started", "effect_confirmed", "failed"]
    assert [p["phase"] for p in rows[1]["phases"]] == ["started", "effect_confirmed", "completed"]
    effects = [r["phases"][1] for r in rows]
    assert effects[0]["artifact_id"] == effects[1]["artifact_id"] == second.json()["artifact_id"]
    assert [e["replayed"] for e in effects] == [False, True]
    assert all(r["client_received"] is None and r["response_state"] == "prepared" for r in rows)
    assert all(r["tool_call_id"] == "logical" for r in rows)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    # Compatibility rows preserve the old stages, but are not physical request counts.
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [200, 503, 200]


def test_rollback_has_no_confirmed_effect_and_keeps_logical_binding(
    client, engine, context, corpus, monkeypatch
):
    service = client.app.state.execution
    original = service.tool_attempt

    def broken(conn, run_id, call, status, **kwargs):
        original(conn, run_id, call, status, **kwargs)
        if status == 200:
            raise SQLAlchemyError("SYNTHETIC-ROLLBACK")

    monkeypatch.setattr(service, "tool_attempt", broken)
    response = send(client, "salvar_minuta", write_body(context, corpus))
    assert response.status_code == 503
    rows = physical(client, engine, context)
    assert len(rows) == 1 and rows[0]["http_status"] == 503
    assert [p["phase"] for p in rows[0]["phases"]] == ["started", "failed"]
    monkeypatch.setattr(service, "tool_attempt", original)
    assert send(client, "salvar_minuta", write_body(context, corpus)).status_code == 200
    assert len(physical(client, engine, context)) == 2


def test_rejected_input_and_invalid_reuse_each_have_one_physical_attempt(client, engine, context):
    assert send(client, "buscar_documentos", context).status_code == 422
    assert send(client, "consultar_processo", context).status_code == 409
    rows = physical(client, engine, context)
    assert [r["http_status"] for r in rows] == [422, 409]
    assert all(len(r["phases"]) == 2 for r in rows)
    assert rows[0]["args_sha256"] != rows[1]["args_sha256"]


def test_unauthenticated_request_is_not_attributed_to_untrusted_run(client, engine, context):
    response = client.post(
        "/tools/consultar_processo", headers={"Authorization": "Bearer invalid"}, json=context
    )
    assert response.status_code == 401
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(physical_tool_attempts).where(physical_tool_attempts.c.http_status == 401)
            )
            .mappings()
            .all()
        )
    assert row and all(r["run_id"] is None and r["tool_call_id"] is None for r in row)


def test_parallel_requests_keep_physical_identity_and_one_effect(client, engine, context, corpus):
    body = write_body(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: send(client, "salvar_minuta", body), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["artifact_id"] for r in responses}) == 1
    rows = physical(client, engine, context)
    assert len(rows) == 2 and len({r["attempt_id"] for r in rows}) == 2
    assert sorted(r["phases"][1]["replayed"] for r in rows) == [False, True]


def test_read_does_not_claim_client_receipt(client, engine, context):
    assert send(client, "consultar_processo", context).status_code == 200
    row = physical(client, engine, context)[0]
    assert [p["phase"] for p in row["phases"]] == ["started", "completed"]
    assert row["http_status"] == 200 and row["client_received"] is None


def test_0006_preserves_legacy_without_inventing_physical_attempts(client, engine, context):
    assert send(client, "consultar_processo", context).status_code == 200
    before = history(client, engine, context["run_id"])
    migrate(engine, "0005", downgrade=True)
    assert "physical_tool_attempts" not in inspect(engine).get_table_names()
    migrate(engine)
    assert history(client, engine, context["run_id"]) == before
    assert physical(client, engine, context) == []
    with engine.connect() as conn:
        assert (
            conn.execute(select(func.count()).select_from(physical_tool_phases)).scalar_one() == 0
        )
    assert send(client, "consultar_processo", context).status_code == 200
    assert len(physical(client, engine, context)) == 1


def test_phase_order_does_not_depend_on_wall_clock_resolution(
    client, engine, context, corpus, monkeypatch
):
    import time

    fixed = time.time()
    monkeypatch.setattr("services.backend.tracking.time.time", lambda: fixed)
    assert send(client, "salvar_minuta", write_body(context, corpus)).status_code == 200
    row = physical(client, engine, context)[0]
    assert len({p["recorded_at"] for p in row["phases"]}) == 1
    assert [p["phase"] for p in row["phases"]] == ["started", "effect_confirmed", "completed"]


def test_completion_collection_failure_remains_explicitly_unknown(
    client, engine, context, corpus, caplog
):
    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "UPDATE physical_tool_attempts" in statement and "http_status" in statement:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-COLLECTOR")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = send(client, "salvar_minuta", write_body(context, corpus))
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 200
    row = physical(client, engine, context)[0]
    assert row["response_state"] == "started" and row["http_status"] is None
    assert row["finished_at"] is None and row["client_received"] is None
    assert [p["phase"] for p in row["phases"]] == ["started", "effect_confirmed"]
    assert row["attempt_id"] in caplog.text and "SYNTHETIC-PRIVATE" not in caplog.text


def test_internal_failure_prepares_safe_response_without_inventing_client_receipt(
    client, engine, context, monkeypatch
):
    def interrupted(*args):
        raise RuntimeError("SYNTHETIC-INTERRUPTED")

    monkeypatch.setattr("services.backend.tools.ToolService.process", interrupted)
    response = send(client, "consultar_processo", context)
    assert response.status_code == 500 and response.json()["code"] == "internal_error"
    assert "SYNTHETIC-INTERRUPTED" not in response.text
    row = physical(client, engine, context)[0]
    assert row["response_state"] == "prepared" and row["http_status"] == 500
    assert row["code"] == "internal_error" and row["client_received"] is None
    assert [p["phase"] for p in row["phases"]] == ["started", "failed"]


def test_transport_loss_retries_as_two_physical_requests(client, engine, context, corpus):
    import json

    import httpx

    from agents.interface import ToolClient

    seen = []

    def respond(request):
        seen.append(request.content)
        response = client.post(
            request.url.path, headers=dict(request.headers), json=json.loads(request.content)
        )
        assert response.status_code == 200
        if len(seen) == 1:
            raise httpx.ReadTimeout("Synthetic lost receipt", request=request)
        return httpx.Response(200, json=response.json())

    tools = ToolClient("http://test", "unused", context, client.headers["X-Run-Token"])
    tools.client.close()
    tools.client = httpx.Client(
        transport=httpx.MockTransport(respond),
        base_url="http://test",
        headers={**client.worker_headers, "X-Run-Token": client.headers["X-Run-Token"]},
    )
    body = write_body(context, corpus)
    try:
        result = tools.call("salvar_minuta", {k: v for k, v in body.items() if k not in context})
    finally:
        tools.close()
    assert result["replayed"] and len(seen) == 2 and seen[0] == seen[1]
    rows = physical(client, engine, context)
    assert len(rows) == 2 and all(
        r["http_status"] == 200 and r["client_received"] is None for r in rows
    )
    assert rows[0]["tool_call_id"] == rows[1]["tool_call_id"]
    assert rows[0]["phases"][1]["artifact_id"] == rows[1]["phases"][1]["artifact_id"]

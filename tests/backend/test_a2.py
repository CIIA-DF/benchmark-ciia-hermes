"""A2: experimental declarations reconciled with persisted server observations."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import ExperimentRun
from services.backend.schema import (
    artifacts,
    events,
    logical_tool_calls,
    physical_tool_attempts,
    physical_tool_phases,
    runs,
)
from tests.backend.test_tool_calls import write_body


def call(call_id, tool="consultar_processo", status="ok", artifact_id=None):
    return {
        "tool_call_id": call_id,
        "tool": tool,
        "status": status,
        "duration_ms": 987654.0,
        "artifact_id": artifact_id,
    }


def result(context, calls, ids=(), status="succeeded"):
    report = ExperimentRun(
        **context,
        task_id="DEV-001",
        split="development",
        executor="simulation",
        repetition=1,
        code_commit="synthetic-a2",
        harness_version="test",
        adapter_version="test",
        model="not-called",
        endpoint_id="none",
        prompt_sha256="0" * 64,
        parameters={},
        started_at=datetime.now(UTC),
        latency_ms=1234567.0,
        tool_calls=calls,
        agent_declared_success=False,
        persisted_artifact_ids=list(ids),
        verified_success=None,
        evaluator=None,
    )
    return {
        "status": status,
        "answer": "Synthetic final answer" if status == "succeeded" else "",
        "experiment": report.model_dump(mode="json"),
    }


def finish(client, context, payload):
    return client.post(f"/runs/{context['run_id']}/result", json=payload)


def assert_rejected(response):
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A2" not in response.text


def assert_open(engine, context):
    with engine.connect() as conn:
        row = conn.execute(select(runs).where(runs.c.run_id == context["run_id"])).mappings().one()
        assert row["status"] == "running" and row["result"] is None
        assert (
            conn.execute(
                select(func.count())
                .select_from(events)
                .where(events.c.run_id == context["run_id"], events.c.kind == "done")
            ).scalar_one()
            == 0
        )


def test_never_executed_is_rejected(client, context, engine):
    for status in ("ok", "error"):
        assert_rejected(
            finish(client, context, result(context, [call("never-executed", status=status)]))
        )
        assert_open(engine, context)


def test_closed_call_set_status_deltas_and_terminal_replay(client, context, engine):
    assert (
        client.post(
            "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "read-ok"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/tools/ler_documento",
            json={**context, "document_id": "PRIVATE-A2-missing"},
            headers={"X-Tool-Call-Id": "read-error"},
        ).status_code
        == 404
    )
    good = result(context, [call("read-ok"), call("read-error", "ler_documento", "error")])
    reports = []
    for label, calls in {
        "omitted": good["experiment"]["tool_calls"][:1],
        "duplicate": [*good["experiment"]["tool_calls"], call("read-ok")],
        "tool mismatch": [
            call("read-ok", "buscar_documentos"),
            call("read-error", "ler_documento", "error"),
        ],
        "false success": [call("read-ok"), call("read-error", "ler_documento")],
        "read artifact": [
            call("read-ok", artifact_id=str(uuid4())),
            call("read-error", "ler_documento", "error"),
        ],
    }.items():
        bad = deepcopy(good)
        bad["experiment"]["tool_calls"] = calls
        reports.append((label, bad))
    for label, payload in reports:
        response = finish(client, context, payload)
        assert response.status_code == 422, label
        assert_rejected(response)
        assert_open(engine, context)
    assert (
        client.post(
            f"/runs/{context['run_id']}/events",
            json={"event_id": str(uuid4()), "kind": "text_delta", "text": good["answer"]},
        ).status_code
        == 200
    )
    inconsistent = {**good, "answer": "PRIVATE-A2 different answer"}
    assert_rejected(finish(client, context, inconsistent))
    accepted = finish(client, context, good)
    assert accepted.status_code == 200
    assert accepted.json()["result"]["experiment"] == good["experiment"]
    assert finish(client, context, good).status_code == 200
    # Late observations must not invalidate a replay of the already accepted identical result.
    assert (
        client.post(
            "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "late-call"}
        ).status_code
        == 409
    )
    assert finish(client, context, good).status_code == 200
    changed = deepcopy(good)
    changed["experiment"]["tool_calls"][0]["duration_ms"] += 1.0
    assert finish(client, context, changed).status_code == 409
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(events)
                .where(events.c.run_id == context["run_id"], events.c.kind == "done")
            ).scalar_one()
            == 1
        )


@pytest.mark.parametrize("tool", ["salvar_minuta", "registrar_pendencia"])
def test_artifacts_must_match_the_declared_call(client, context, corpus, engine, tool):
    receipts = []
    for index in range(2):
        body = write_body(context, corpus, key=f"a2-{index}")
        if tool == "registrar_pendencia":
            body["requirement_id"] = "REQ-DEMO-001"
        response = client.post(
            f"/tools/{tool}", json=body, headers={"X-Tool-Call-Id": f"write-{index}"}
        )
        assert response.status_code == 200
        receipts.append(response.json()["artifact_id"])
    good = result(
        context,
        [call(f"write-{i}", tool, artifact_id=aid) for i, aid in enumerate(receipts)],
        receipts,
    )
    variants = []
    swapped = deepcopy(good)
    swapped["experiment"]["tool_calls"][0]["artifact_id"] = receipts[1]
    variants.append(swapped)
    for ids in ([str(uuid4())], receipts[:1], receipts + receipts[:1]):
        bad = deepcopy(good)
        bad["experiment"]["persisted_artifact_ids"] = ids
        variants.append(bad)
    missing = deepcopy(good)
    missing["experiment"]["tool_calls"][0]["artifact_id"] = None
    variants.append(missing)
    for payload in variants:
        assert_rejected(finish(client, context, payload))
        assert_open(engine, context)
    assert finish(client, context, good).status_code == 200
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 2
        )


@pytest.mark.parametrize("tool,retry", [("salvar_minuta", True), ("registrar_pendencia", False)])
def test_post_commit_failure_preserves_observed_effect_and_client_outcome(
    client, context, corpus, engine, tool, retry
):
    service = client.app.state.execution
    reads = []

    def lost_receipt(conn, cursor, statement, parameters, execution_context, many):
        if "FROM artifacts" in statement:
            reads.append(statement)
            if len(reads) == 3:
                raise SQLAlchemyError("PRIVATE-A2 post-commit receipt")

    body = write_body(context, corpus, key="a2-postcommit")
    if tool == "registrar_pendencia":
        body["requirement_id"] = "REQ-DEMO-001"
    headers = {"X-Tool-Call-Id": "write-uncertain"}
    # Match the established F0 probe: fail the independent post-commit read.
    event.listen(engine, "before_cursor_execute", lost_receipt)
    try:
        assert client.post(f"/tools/{tool}", json=body, headers=headers).status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", lost_receipt)
    with engine.connect() as conn:
        aid = conn.execute(
            select(artifacts.c.artifact_id).where(artifacts.c.run_id == context["run_id"])
        ).scalar_one()
    with engine.connect() as conn:
        observed = service.tracking.history(conn, context["run_id"])
    assert observed[0]["phases"][1]["phase"] == "effect_confirmed"
    assert observed[0]["phases"][1]["artifact_id"] == aid
    # A confirmed effect alone does not prove that a valid success response was prepared.
    assert_rejected(
        finish(
            client,
            context,
            result(context, [call("write-uncertain", tool, artifact_id=aid)], [aid]),
        )
    )
    if retry:
        replay = client.post(f"/tools/{tool}", json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()["replayed"]
        payload = result(context, [call("write-uncertain", tool, artifact_id=aid)], [aid])
    else:
        payload = result(context, [call("write-uncertain", tool, "error")], status="failed")
    response = finish(client, context, payload)
    assert response.status_code == 200
    assert response.json()["result"]["experiment"] == payload["experiment"]
    assert len(response.json()["artifacts"]) == 1
    with engine.connect() as conn:
        physical = service.tracking.history(conn, context["run_id"])
    assert len(physical) == (2 if retry else 1)
    assert all(r["client_received"] is None for r in physical)


def test_physical_response_unknown_with_confirmed_execution_is_representable(
    client, context, engine, monkeypatch
):
    def unavailable(conn, cursor, statement, parameters, execution_context, many):
        if "UPDATE physical_tool_attempts" in statement and "http_status" in statement:
            raise SQLAlchemyError("PRIVATE-A2 collector")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post(
            "/tools/consultar_processo",
            json=context,
            headers={"X-Tool-Call-Id": "response-unknown"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 200
    with engine.connect() as conn:
        history = client.app.state.execution.tracking.history(conn, context["run_id"])
    assert history[0]["http_status"] is None
    assert finish(client, context, result(context, [call("response-unknown")])).status_code == 200


def test_failure_without_experiment_preserves_unobserved_transport_path(client, context):
    response = finish(
        client, context, {"status": "failed", "answer": "", "error_code": "adapter_error"}
    )
    assert response.status_code == 200 and response.json()["result"]["experiment"] is None


def test_budget_rejection_without_logical_reservation_is_still_attributable(client, context):
    client.app.state.execution.max_tool_calls = 1
    assert (
        client.post(
            "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "within-budget"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "over-budget"}
        ).status_code
        == 409
    )
    payload = result(context, [call("within-budget"), call("over-budget", status="error")])
    assert finish(client, context, payload).status_code == 200


def test_legacy_call_identity_is_checked_without_inventing_physical_history(
    client, context, engine
):
    assert (
        client.post(
            "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "legacy-read"}
        ).status_code
        == 200
    )
    # Only the disposable test database is changed to represent a pre-F0/0005 record.
    with engine.begin() as conn:
        ids = select(physical_tool_attempts.c.attempt_id).where(
            physical_tool_attempts.c.run_id == context["run_id"]
        )
        conn.execute(delete(physical_tool_phases).where(physical_tool_phases.c.attempt_id.in_(ids)))
        conn.execute(
            delete(physical_tool_attempts).where(
                physical_tool_attempts.c.run_id == context["run_id"]
            )
        )
        conn.execute(
            delete(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
        )
    assert finish(client, context, result(context, [call("legacy-read")])).status_code == 200
    with engine.connect() as conn:
        assert client.app.state.execution.tracking.history(conn, context["run_id"]) == []


def test_response_unknown_without_completed_operation_cannot_claim_success(
    client, context, engine, monkeypatch
):
    def collector_failure(conn, cursor, statement, parameters, execution_context, many):
        if "UPDATE physical_tool_attempts" in statement and "http_status" in statement:
            raise SQLAlchemyError("PRIVATE-A2 collector")

    def interrupted(*args):
        raise RuntimeError("PRIVATE-A2 interrupted before domain completion")

    monkeypatch.setattr("services.backend.tools.ToolService.process", interrupted)
    event.listen(engine, "before_cursor_execute", collector_failure)
    try:
        assert (
            client.post(
                "/tools/consultar_processo",
                json=context,
                headers={"X-Tool-Call-Id": "unknown-incomplete"},
            ).status_code
            == 500
        )
    finally:
        event.remove(engine, "before_cursor_execute", collector_failure)
    assert_rejected(finish(client, context, result(context, [call("unknown-incomplete")])))
    assert (
        finish(
            client,
            context,
            result(context, [call("unknown-incomplete", status="error")], status="failed"),
        ).status_code
        == 200
    )


def test_client_transport_loss_with_prepared_200s_keeps_one_effect(client, context, corpus, engine):
    from agents.interface import ToolClient

    def lose_response(request):
        response = client.post(
            request.url.path, headers=dict(request.headers), content=request.content
        )
        assert response.status_code == 200
        raise httpx.ReadTimeout("PRIVATE-A2 lost response", request=request)

    tools = ToolClient("http://test", "unused", context, client.headers["X-Run-Token"])
    tools.client.close()
    tools.client = httpx.Client(
        transport=httpx.MockTransport(lose_response),
        base_url="http://test",
        headers={**client.worker_headers, "X-Run-Token": client.headers["X-Run-Token"]},
    )
    body = write_body(context, corpus, key="a2-transport")
    try:
        with pytest.raises(httpx.ReadTimeout):
            tools.call("salvar_minuta", {k: v for k, v in body.items() if k not in context})
    finally:
        tools.close()
    assert len(tools.calls) == 1 and tools.calls[0].status == "error"
    assert tools.calls[0].artifact_id is None
    payload = result(context, tools.calls, status="failed")
    accepted = finish(client, context, payload)
    assert accepted.status_code == 200 and len(accepted.json()["artifacts"]) == 1
    assert accepted.json()["result"]["experiment"]["persisted_artifact_ids"] == []
    with engine.connect() as conn:
        history = client.app.state.execution.tracking.history(conn, context["run_id"])
        assert len(history) == 3 and all(item["http_status"] == 200 for item in history)
        assert all(item["client_received"] is None for item in history)


def test_claimed_artifact_integrity_and_foreign_run_are_checked(client, context, corpus, engine):
    first = client.post(
        "/tools/salvar_minuta",
        json=write_body(context, corpus),
        headers={"X-Tool-Call-Id": "original-write"},
    )
    assert first.status_code == 200
    receipt = first.json()
    aid = receipt["artifact_id"]
    good = result(context, [call("original-write", "salvar_minuta", artifact_id=aid)], [aid])
    with engine.begin() as conn:
        conn.execute(
            update(artifacts)
            .where(artifacts.c.artifact_id == aid)
            .values(receipt={**receipt, "content_sha256": "0" * 64})
        )
    bad = finish(client, context, good)
    assert bad.status_code == 500 and bad.json()["code"] == "invalid_response"
    assert_open(engine, context)
    with engine.begin() as conn:
        conn.execute(
            update(artifacts).where(artifacts.c.artifact_id == aid).values(receipt=receipt)
        )
    other = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            **{
                key: context[key]
                for key in ("process_id", "corpus_version", "requirements_version")
            },
            "task": "Synthetic foreign run",
            "task_id": "DEV-001",
            "idempotency_key": str(uuid4()),
        },
    )
    assert other.status_code == 202
    claimed = client.post(
        "/runs/claim", json={"executor": "simulation", "run_id": other.json()["run_id"]}
    )
    assert claimed.status_code == 200
    foreign = client.post(
        "/tools/salvar_minuta",
        json=write_body(claimed.json()["context"], corpus),
        headers={"X-Run-Token": claimed.json()["run_token"], "X-Tool-Call-Id": "foreign-write"},
    )
    assert foreign.status_code == 200
    foreign_id = foreign.json()["artifact_id"]
    assert_rejected(
        finish(
            client,
            context,
            result(
                context,
                [call("original-write", "salvar_minuta", artifact_id=foreign_id)],
                [foreign_id],
            ),
        )
    )
    assert_open(engine, context)
    assert finish(client, context, good).status_code == 200

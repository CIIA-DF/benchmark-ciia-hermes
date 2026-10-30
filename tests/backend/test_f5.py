"""F5: reusable integrity boundary and one physical request per write/retry."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import ToolContext
from services.backend.artifact_integrity import validate_artifact
from services.backend.errors import ToolFailure
from services.backend.schema import artifacts, logical_tool_calls
from tests.backend.test_tool_calls import write_body


def body(context, corpus):
    return {**write_body(context, corpus), "requirement_id": "REQ-DEMO-001"}


def write(client, payload, call_id="pendency-f5"):
    return client.post(
        "/tools/registrar_pendencia", headers={"X-Tool-Call-Id": call_id}, json=payload
    )


def observed(client, engine, context):
    with engine.connect() as conn:
        rows = client.app.state.execution.tracking.history(conn, context["run_id"])
        count = conn.execute(
            select(func.count())
            .select_from(artifacts)
            .where(artifacts.c.run_id == context["run_id"])
        ).scalar_one()
    return rows, count


def test_concurrent_pendency_has_two_physical_requests_and_one_effect(
    client, engine, context, corpus
):
    payload = body(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: write(client, payload), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["artifact_id"] for r in responses}) == 1
    rows, count = observed(client, engine, context)
    assert count == 1 and len(rows) == 2 and len({r["attempt_id"] for r in rows}) == 2
    assert sorted(r["phases"][1]["replayed"] for r in rows) == [False, True]
    assert all(
        [p["phase"] for p in r["phases"]] == ["started", "effect_confirmed", "completed"]
        for r in rows
    )
    assert all(r["client_received"] is None for r in rows)
    assert all(r["phases"][1]["artifact_id"] == responses[0].json()["artifact_id"] for r in rows)


def test_pendency_rollback_discards_effect_phase_and_recovers_same_identity(
    client, engine, context, corpus, monkeypatch
):
    service = client.app.state.execution
    service.max_tool_calls = 1
    original = service.tool_attempt

    def broken(conn, run_id, call, status, **kwargs):
        original(conn, run_id, call, status, **kwargs)
        if status == 200:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-ROLLBACK")

    monkeypatch.setattr(service, "tool_attempt", broken)
    payload = body(context, corpus)
    failed = write(client, payload)
    assert failed.status_code == 503 and "SYNTHETIC-PRIVATE" not in failed.text
    rows, count = observed(client, engine, context)
    assert count == 0 and len(rows) == 1
    assert [p["phase"] for p in rows[0]["phases"]] == ["started", "failed"]
    monkeypatch.setattr(service, "tool_attempt", original)
    recovered = write(client, payload)
    assert recovered.status_code == 200 and not recovered.json()["replayed"]
    rows, count = observed(client, engine, context)
    assert count == 1 and len(rows) == 2
    with engine.connect() as conn:
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert all(r["tool_call_id"] == logical["tool_call_id"] == "pendency-f5" for r in rows)


@pytest.mark.parametrize("corruption", ["context", "tool", "receipt_id"])
def test_integrity_validator_uses_trusted_run_context_without_write_request(
    client, engine, context, corpus, corruption
):
    response = write(client, body(context, corpus))
    assert response.status_code == 200
    with engine.connect() as conn:
        stored = dict(
            conn.execute(
                select(artifacts).where(artifacts.c.artifact_id == response.json()["artifact_id"])
            )
            .mappings()
            .one()
        )
    snapshot = deepcopy(stored)
    trusted = ToolContext.model_validate(context)
    validated = validate_artifact(
        stored, expected_tool="registrar_pendencia", expected_context=trusted
    )
    http = client.get(
        f"/artifacts/{response.json()['artifact_id']}", headers=client.operator_headers
    )
    assert http.status_code == 200 and validated.model_dump(mode="json") == http.json()
    assert stored == snapshot
    bad = deepcopy(stored)
    expected = trusted
    if corruption == "context":
        expected = ToolContext.model_validate({**context, "run_id": str(uuid4())})
    elif corruption == "tool":
        bad["tool"] = "salvar_minuta"
    else:
        bad["receipt"]["artifact_id"] = str(uuid4())
    with pytest.raises(ToolFailure) as error:
        validate_artifact(bad, expected_tool="registrar_pendencia", expected_context=expected)
    assert error.value.status == 500 and error.value.error.code == "invalid_response"
    rows, count = observed(client, engine, context)
    assert len(rows) == count == 1
    # Preparation for A1 only: GET retains its current implementation in F5.
    again = client.get(
        f"/artifacts/{response.json()['artifact_id']}", headers=client.operator_headers
    )
    assert again.status_code == 200 and again.json() == http.json()

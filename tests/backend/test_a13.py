"""A13: each tool's HTTP boundary and durable physical-request admission."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, insert, select, update

from contracts.catalog import TOOLS
from contracts.models import ToolError
from services.backend.auth import authenticate
from services.backend.http_boundary import MAX_BODY_BYTES
from services.backend.schema import (
    artifacts,
    physical_tool_attempts,
    physical_tool_phases,
    principals,
)
from tests.backend.test_execution import claim, conversation, send
from tests.backend.test_tool_calls import write_body


def payload(tool, context, corpus):
    if tool in {"registrar_pendencia", "salvar_minuta"}:
        value = write_body(context, corpus)
        if tool == "registrar_pendencia":
            value["requirement_id"] = "REQ-DEMO-001"
        return value
    if tool == "buscar_documentos":
        return {**context, "query": "material"}
    if tool == "ler_documento":
        return {**context, "document_id": corpus[1].document_id}
    return context


def seed(engine, rid, count):
    identities = [str(uuid4()) for _ in range(count)]
    with engine.begin() as conn:
        conn.execute(
            insert(physical_tool_attempts),
            [
                dict(
                    attempt_id=identity,
                    tool="consultar_processo",
                    method="POST",
                    run_id=rid,
                    tool_call_id=f"seed-{index}",
                    args_sha256="a" * 64,
                    started_at=float(index),
                    finished_at=float(index),
                    response_state="prepared",
                    http_status=422,
                    code="validation_error",
                    client_received=None,
                )
                for index, identity in enumerate(identities)
            ],
        )
        conn.execute(
            insert(physical_tool_phases),
            [
                dict(attempt_id=identity, phase=phase, recorded_at=0.0)
                for identity in identities
                for phase in ("started", "failed")
            ],
        )
    return identities


def attempts(engine, rid):
    with engine.connect() as conn:
        return [
            dict(item)
            for item in conn.execute(
                select(physical_tool_attempts).where(physical_tool_attempts.c.run_id == rid)
            ).mappings()
        ]


@pytest.mark.parametrize("tool", list(TOOLS))
def test_each_tool_has_safe_http_auth_lease_identity_body_and_output(
    client, corpus, context, engine, tool
):
    path = f"/tools/{tool}"
    body = payload(tool, context, corpus)
    for headers, status in [
        ({"Authorization": ""}, 401),
        (client.operator_headers, 403),
        ({"X-Run-Token": ""}, 403),
        ({"X-Run-Token": "wrong"}, 403),
    ]:
        response = client.post(path, headers=headers, json=body)
        assert response.status_code == status
        assert ToolError.model_validate(response.json()).code in {"unauthorized", "forbidden"}
        assert response.headers["cache-control"] == "no-store"
        if status == 401:
            assert response.headers["www-authenticate"] == "Bearer"
    assert client.post(path, json={}).status_code == 422
    assert client.post(path, headers={"X-Tool-Call-Id": "invalid id"}, json=body).status_code == 422
    oversized = client.post(path, content=b"x" * (MAX_BODY_BYTES + 1))
    assert oversized.status_code == 413 and oversized.json()["code"] == "payload_too_large"
    response = client.post(path, headers={"X-Tool-Call-Id": "a13-valid"}, json=body)
    assert response.status_code == 200, response.text
    TOOLS[tool].output_model.model_validate(response.json())
    replay = client.post(path, headers={"X-Tool-Call-Id": "a13-valid"}, json=body)
    assert replay.status_code == 200
    assert response.headers["cache-control"] == replay.headers["cache-control"] == "no-store"
    if tool in {"registrar_pendencia", "salvar_minuta"}:
        assert response.json()["artifact_id"] == replay.json()["artifact_id"]
        assert replay.json()["replayed"] is True
    else:
        assert response.json() == replay.json()
    rows = attempts(engine, context["run_id"])
    assert len({item["attempt_id"] for item in rows}) == len(rows)
    assert all(item["client_received"] is None for item in rows)


@pytest.mark.parametrize("tool", list(TOOLS))
def test_executor_mismatch_rejects_each_tool(client, corpus, context, engine, tool):
    actor = authenticate(engine, client.worker_headers["Authorization"])
    with engine.begin() as conn:
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == actor["principal_id"])
            .values(executor="hermes")
        )
    response = client.post(f"/tools/{tool}", json=payload(tool, context, corpus))
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_real_thousandth_request_allowed_and_replay_cannot_bypass_ceiling(client, context, engine):
    original = set(seed(engine, context["run_id"], 999))
    for expected in (200, 429, 429):
        response = client.post(
            "/tools/consultar_processo", headers={"X-Tool-Call-Id": "last"}, json=context
        )
        assert response.status_code == expected
        if expected == 429:
            assert response.json()["code"] == "resource_limit"
            assert response.json()["retryable"] is False
            assert response.headers["cache-control"] == "no-store"
    rows = attempts(engine, context["run_id"])
    assert len(rows) == 1002  # Denials remain audited; admission stops after request 1000.
    assert original <= {item["attempt_id"] for item in rows}
    added = [item for item in rows if item["attempt_id"] not in original]
    assert sorted(item["http_status"] for item in added) == [200, 429, 429]
    assert all(item["tool_call_id"] == "last" and item["client_received"] is None for item in added)


def test_invalid_body_method_and_oversize_count_without_effects(
    client, context, engine, monkeypatch
):
    from services.backend import execution

    monkeypatch.setattr(execution, "MAX_PHYSICAL_ATTEMPTS_PER_RUN", 3)
    path = "/tools/consultar_processo"
    assert client.post(path, content=b"{").status_code == 422
    assert client.get(path).status_code == 405
    assert client.post(path, content=b"x" * (MAX_BODY_BYTES + 1)).status_code == 413
    response = client.post(path, json=context)
    assert response.status_code == 429
    assert sorted(item["http_status"] for item in attempts(engine, context["run_id"])) == [
        405,
        413,
        422,
        429,
    ]


def test_concurrent_last_slot_has_one_write_and_distinct_physical_receipts(
    client, context, corpus, engine
):
    seed(engine, context["run_id"], 999)
    body = write_body(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/tools/salvar_minuta", headers={"X-Tool-Call-Id": "same-last"}, json=body
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 429]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    rows = attempts(engine, context["run_id"])
    assert len(rows) == 1001 and len({item["attempt_id"] for item in rows}) == 1001


def test_quota_of_one_run_does_not_block_another(client, context, corpus, engine):
    seed(engine, context["run_id"], 1000)
    assert client.post("/tools/consultar_processo", json=context).status_code == 429
    send(client, conversation(client, corpus))
    second, headers = claim(client)
    response = client.post("/tools/consultar_processo", headers=headers, json=second["context"])
    assert response.status_code == 200
    assert len(attempts(engine, second["run_id"])) == 1

"""Regressions for typed HTTP boundaries and current authorization checks."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete

from contracts.execution import ClaimedRun
from contracts.models import ToolCallRecord
from services.backend.schema import permissions


@pytest.mark.parametrize("limit", [True, "2", 2.0])
def test_search_rejects_coerced_numbers_without_echo(client, context, limit):
    response = client.post(
        "/tools/buscar_documentos", json={**context, "query": "synthetic", "limit": limit}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "synthetic" not in response.text


@pytest.mark.parametrize("page", [True, "1", 1.0])
def test_read_rejects_coerced_pages(client, context, page):
    response = client.post(
        "/tools/ler_documento", json={**context, "document_id": "SYNTHETIC", "pages": [page]}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("authorization", ["", "Basic synthetic", "Bearer invalid-synthetic"])
def test_invalid_credential_is_safe(client, authorization):
    response = client.get("/processos", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert "invalid-synthetic" not in response.text


def test_revoked_worker_grant_denies_tool(client, context, engine):
    from services.backend.auth import authenticate

    actor = authenticate(engine, client.worker_headers["Authorization"])
    with engine.begin() as connection:
        connection.execute(
            delete(permissions).where(permissions.c.principal_id == actor["principal_id"])
        )
    response = client.post("/tools/consultar_processo", json=context)
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_claim_has_closed_nested_contracts(client, context):
    # The context fixture reserves the first run; create and reserve a second one.
    scope = {key: context[key] for key in ("process_id", "corpus_version", "requirements_version")}
    queued = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            **scope,
            "task": "Synthetic task",
            "task_id": "STRICT",
            "idempotency_key": str(uuid4()),
        },
    )
    assert queued.status_code == 202
    claimed = client.post(
        "/runs/claim",
        headers=client.worker_headers,
        json={"executor": "simulation", "run_id": queued.json()["run_id"]},
    )
    assert claimed.status_code == 200
    value = claimed.json()
    assert isinstance(ClaimedRun.model_validate(value).context, dict)
    mutations = [
        ("context", "process_id", None),
        ("context", "unexpected", "synthetic"),
        ("task_metadata", "repetition", True),
        ("task_metadata", "split", "unknown"),
    ]
    for section, key, replacement in mutations:
        invalid = deepcopy(value)
        invalid[section][key] = replacement
        with pytest.raises(ValidationError):
            ClaimedRun.model_validate(invalid)
    invalid = deepcopy(value)
    invalid["history"][0]["role"] = "system"
    with pytest.raises(ValidationError):
        ClaimedRun.model_validate(invalid)


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), "1", True])
def test_telemetry_rejects_non_finite_or_coerced_duration(duration):
    with pytest.raises(ValidationError):
        ToolCallRecord(
            tool_call_id="synthetic", tool="consultar_processo", duration_ms=duration, status="ok"
        )


def test_tool_record_rejects_unknown_tool():
    with pytest.raises(ValidationError):
        ToolCallRecord(tool_call_id="synthetic", tool="invented", duration_ms=0, status="ok")


def test_http_response_validation_rejects_malformed_run_context(client, context, monkeypatch):
    original = client.app.state.execution.get_run

    def invalid(*args):
        result = original(*args)
        result["context"] = {"run_id": context["run_id"]}
        return result

    monkeypatch.setattr(client.app.state.execution, "get_run", invalid)
    response = client.get(f"/runs/{context['run_id']}", headers=client.operator_headers)
    assert response.status_code == 500
    assert response.json()["code"] == "invalid_response"
    assert "context" not in response.text and context["run_id"] not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_health_and_nested_openapi_are_typed(client):
    assert client.get("/health").json() == {"status": "ok", "contract_version": "0.3"}
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("RunContext", "HistoryMessage", "TaskMetadata", "HealthResponse"):
        assert schemas[name]["additionalProperties"] is False
    assert set(schemas["RunContext"]["required"]) == {
        "run_id",
        "process_id",
        "corpus_version",
        "requirements_version",
    }

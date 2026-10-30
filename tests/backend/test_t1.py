"""HTTP and consumer regressions for consultar_processo consistency."""

from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import ToolCallError, tool_outcome
from contracts.models import ProcessResult
from services.backend.corpus import CorpusRepository
from services.backend.storage import documents, processes
from tests.backend.test_tool_calls import history


def response(client, context):
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize("field", ["process_id", "corpus_version", "requirements_version"])
def test_nested_process_must_match_envelope(client, context, field):
    value = response(client, context)
    value["process"][field] = "OTHER"
    with pytest.raises(ValidationError):
        ProcessResult.model_validate(value)
    http = httpx.Response(
        200, json=value, request=httpx.Request("POST", "http://test/tools/consultar_processo")
    )
    with pytest.raises(ToolCallError):
        tool_outcome(http, "consultar_processo", context)


def test_duplicate_inventory_is_rejected_on_server_and_client(client, context, monkeypatch):
    value = response(client, context)
    duplicate = value["inventory"] * 2
    monkeypatch.setattr(CorpusRepository, "inventory", lambda *args: duplicate)
    result = client.post(
        "/tools/consultar_processo", headers={"X-Tool-Call-Id": "duplicates"}, json=context
    )
    assert result.status_code == 500
    assert result.json()["code"] == "invalid_response"
    assert not result.json()["retryable"]
    invalid = {**value, "inventory": duplicate}
    with pytest.raises(ToolCallError):
        tool_outcome(
            httpx.Response(
                200,
                json=invalid,
                request=httpx.Request("POST", "http://test/tools/consultar_processo"),
            ),
            "consultar_processo",
            context,
        )


@pytest.mark.parametrize(
    "field", ["run_id", "process_id", "corpus_version", "requirements_version"]
)
def test_consistent_foreign_envelope_is_rejected_by_client(client, context, field):
    value = response(client, context)
    value[field] = str(uuid4()) if field == "run_id" else "OTHER"
    if field != "run_id":
        value["process"][field] = value[field]
    # Internally coherent, but it is not the authenticated request's response.
    ProcessResult.model_validate(value)
    with pytest.raises(ToolCallError):
        tool_outcome(
            httpx.Response(
                200,
                json=value,
                request=httpx.Request("POST", "http://test/tools/consultar_processo"),
            ),
            "consultar_processo",
            context,
        )


@pytest.mark.parametrize("field", ["document_id", "process_id", "corpus_version"])
def test_corrupt_document_payload_cannot_escape_inventory_scope(client, context, engine, field):
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(documents).where(
                    documents.c.process_id == context["process_id"],
                    documents.c.corpus_version == context["corpus_version"],
                )
            )
            .mappings()
            .one()
        )
        payload = deepcopy(row["payload"])
        payload[field] = "PRIVATE-SYNTHETIC-REJECTED"
        conn.execute(
            update(documents)
            .where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
                documents.c.document_id == row["document_id"],
            )
            .values(payload=payload)
        )
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 500
    assert result.json()["code"] == "invalid_response"
    assert "PRIVATE-SYNTHETIC-REJECTED" not in result.text
    assert all(item["http_status"] != 200 for item in history(client, engine, context["run_id"]))


@pytest.mark.parametrize("completeness", ["complete", "partial", "unknown"])
def test_coverage_note_and_inventory_survive_transport(client, context, engine, completeness):
    with engine.begin() as conn:
        payload = conn.execute(
            select(processes.c.payload).where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
        ).scalar_one()
        payload = {
            **payload,
            "export_completeness": completeness,
            "export_note": "Synthetic coverage limitation",
        }
        conn.execute(
            update(processes)
            .where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
            .values(payload=payload)
        )
    value = response(client, context)
    parsed = tool_outcome(
        httpx.Response(
            200, json=value, request=httpx.Request("POST", "http://test/tools/consultar_processo")
        ),
        "consultar_processo",
        context,
    )
    assert parsed == value
    assert parsed["process"]["export_completeness"] == completeness
    assert parsed["process"]["export_note"] == "Synthetic coverage limitation"
    assert parsed["inventory"]


def test_versions_missing_and_storage_have_distinct_errors(client, context, engine, monkeypatch):
    mismatched = client.post(
        "/tools/consultar_processo", json={**context, "requirements_version": "OTHER"}
    )
    assert mismatched.status_code == 403
    # A coherent authenticated context whose catalog version changed is a 409.
    with engine.begin() as conn:
        original = conn.execute(
            select(processes.c.payload).where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
        ).scalar_one()
        conn.execute(
            update(processes)
            .where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
            .values(payload={**original, "requirements_version": "OTHER"})
        )
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 409 and result.json()["code"] == "version_mismatch"

    def broken(*args):
        raise SQLAlchemyError("synthetic-private-sql")

    monkeypatch.setattr(CorpusRepository, "process", broken)
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 503 and result.json()["retryable"]
    assert "synthetic-private-sql" not in result.text

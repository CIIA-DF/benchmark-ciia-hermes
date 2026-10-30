"""F3: read identity, exact pages and canonical physical tracking."""

import hashlib

import httpx
import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import tool_outcome
from contracts.models import ReadInput
from services.backend.execution import digest
from services.backend.schema import artifacts, logical_tool_calls
from services.backend.storage import documents


@pytest.mark.parametrize(
    ("scenario", "status", "code"),
    [
        ("full", 200, None),
        ("partial", 200, None),
        ("gaps", 200, None),
        ("missing_document", 404, "not_found"),
        ("missing_page", 404, "not_found"),
        ("corrupt", 500, "invalid_response"),
        ("invalid_pages", 422, "validation_error"),
        ("storage", 503, "storage_unavailable"),
    ],
)
def test_read_pages_and_tracking_stay_coherent(
    client, context, corpus, engine, scenario, status, code
):
    original = corpus[1].model_dump(mode="json")
    body = {**context, "document_id": original["document_id"], "pages": None}
    expected = original
    if scenario == "partial":
        body["pages"] = [original["pages"][0]["number"]]
    elif scenario == "gaps":
        expected = {
            **original,
            "pages": [{**original["pages"][0], "number": 1}, {**original["pages"][1], "number": 7}],
        }
        body["pages"] = [7, 1]
    elif scenario == "missing_document":
        body["document_id"] = "MISSING"
    elif scenario == "missing_page":
        body["pages"] = [999]
    elif scenario == "invalid_pages":
        body["pages"] = []
    if scenario in {"gaps", "corrupt"}:
        with engine.begin() as conn:
            conn.execute(
                update(documents)
                .where(
                    documents.c.process_id == context["process_id"],
                    documents.c.corpus_version == context["corpus_version"],
                    documents.c.document_id == original["document_id"],
                )
                .values(
                    payload=expected
                    if scenario == "gaps"
                    else {**original, "document_id": "SYNTHETIC-PRIVATE-OTHER"}
                )
            )

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM documents" in statement:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-SQL")

    if scenario == "storage":
        event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post(
            "/tools/ler_documento", headers={"X-Tool-Call-Id": "read-f3"}, json=body
        )
    finally:
        if scenario == "storage":
            event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == status and "SYNTHETIC-PRIVATE" not in response.text
    if status == 200:
        result = tool_outcome(
            httpx.Response(
                200,
                json=response.json(),
                request=httpx.Request("POST", "http://test/tools/ler_documento"),
            ),
            "ler_documento",
            context,
            body,
        )
        assert result == response.json()
        assert result["document"]["sha256"] == original["sha256"]
        wanted = (
            expected["pages"]
            if body["pages"] is None
            else [p for p in expected["pages"] if p["number"] in body["pages"]]
        )
        assert result["document"]["pages"] == wanted
        assert result["document"]["document_id"] == body["document_id"]
    else:
        assert response.json()["code"] == code
        assert response.json()["retryable"] is (status == 503)
    with engine.connect() as conn:
        rows = client.app.state.execution.tracking.history(conn, context["run_id"])
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )
    expected_hash = (
        hashlib.sha256(response.request.content).hexdigest()
        if status == 422
        else digest(ReadInput.model_validate(body).model_dump(mode="json"))
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["tool"] == logical["tool"] == "ler_documento"
    assert row["tool_call_id"] == logical["tool_call_id"] == "read-f3"
    assert row["args_sha256"] == logical["args_sha256"] == expected_hash
    assert row["http_status"] == status and row["code"] == code
    assert row["response_state"] == "prepared" and row["client_received"] is None
    assert [p["phase"] for p in row["phases"]] == [
        "started",
        "completed" if status == 200 else "failed",
    ]
    assert all(p["artifact_id"] is None for p in row["phases"])


def test_repeated_partial_read_keeps_one_logical_binding_and_two_physical_requests(
    client, context, corpus, engine
):
    client.app.state.execution.max_tool_calls = 1
    body = {**context, "document_id": corpus[1].document_id, "pages": [1]}
    headers = {"X-Tool-Call-Id": "repeat-read"}
    first = client.post("/tools/ler_documento", headers=headers, json=body)
    second = client.post("/tools/ler_documento", headers=headers, json=body)
    assert first.status_code == second.status_code == 200 and first.json() == second.json()
    assert first.json()["document"]["sha256"] == corpus[1].sha256
    with engine.connect() as conn:
        rows = client.app.state.execution.tracking.history(conn, context["run_id"])
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert len(rows) == 2 and len({r["attempt_id"] for r in rows}) == 2
    assert all(r["tool_call_id"] == logical["tool_call_id"] == "repeat-read" for r in rows)
    assert all(r["args_sha256"] == logical["args_sha256"] and r["http_status"] == 200 for r in rows)
    assert all([p["phase"] for p in r["phases"]] == ["started", "completed"] for r in rows)

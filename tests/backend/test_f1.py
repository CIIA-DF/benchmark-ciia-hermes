"""F1 acceptance: consultar_processo keeps domain contracts and canonical F0 tracking."""

import httpx
import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import tool_outcome
from services.backend.execution import digest
from services.backend.schema import artifacts, logical_tool_calls
from services.backend.storage import chunks, documents, processes


@pytest.mark.parametrize(
    ("scenario", "status", "code"),
    [
        ("normal", 200, None),
        ("empty_inventory", 200, None),
        ("missing", 404, "not_found"),
        ("version", 409, "version_mismatch"),
        ("metadata", 500, "invalid_response"),
        ("inventory", 500, "invalid_response"),
        ("storage", 503, "storage_unavailable"),
    ],
)
def test_process_outcome_has_one_physical_attempt_and_durable_logical_reservation(
    client, context, corpus, engine, scenario, status, code
):
    scope = (
        processes.c.process_id == context["process_id"],
        processes.c.corpus_version == context["corpus_version"],
    )
    with engine.begin() as conn:
        if scenario in {"empty_inventory", "missing"}:
            for table in (chunks, documents):
                conn.execute(
                    delete(table).where(
                        table.c.process_id == context["process_id"],
                        table.c.corpus_version == context["corpus_version"],
                    )
                )
        if scenario == "missing":
            conn.execute(delete(processes).where(*scope))
        elif scenario in {"version", "metadata"}:
            payload = corpus[0].model_dump(mode="json")
            if scenario == "version":
                payload["requirements_version"] = "OTHER"
            else:
                payload.pop("requirements_version")
                payload["export_note"] = "SYNTHETIC-PRIVATE-METADATA"
            conn.execute(update(processes).where(*scope).values(payload=payload))
        elif scenario == "inventory":
            payload = corpus[1].model_dump(mode="json")
            payload["process_id"] = "SYNTHETIC-PRIVATE-OTHER"
            conn.execute(
                update(documents)
                .where(
                    documents.c.process_id == context["process_id"],
                    documents.c.corpus_version == context["corpus_version"],
                    documents.c.document_id == corpus[1].document_id,
                )
                .values(payload=payload)
            )

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM processes" in statement:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-SQL")

    if scenario == "storage":
        event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post(
            "/tools/consultar_processo", headers={"X-Tool-Call-Id": "process-f1"}, json=context
        )
    finally:
        if scenario == "storage":
            event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == status
    assert "SYNTHETIC-PRIVATE" not in response.text
    if status == 200:
        parsed = tool_outcome(
            httpx.Response(
                200,
                json=response.json(),
                request=httpx.Request("POST", "http://test/tools/consultar_processo"),
            ),
            "consultar_processo",
            context,
            context,
        )
        assert parsed == response.json()
        assert parsed["process"]["export_note"] == corpus[0].export_note
        if scenario == "empty_inventory":
            assert parsed["inventory"] == []
        else:
            assert [item["document_id"] for item in parsed["inventory"]] == [corpus[1].document_id]
    else:
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["code"] == code
        assert response.json()["retryable"] is (status == 503)

    with engine.connect() as conn:
        physical = client.app.state.execution.tracking.history(conn, context["run_id"])
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
    assert len(physical) == 1
    observed = physical[0]
    assert observed["tool"] == logical["tool"] == "consultar_processo"
    assert observed["tool_call_id"] == logical["tool_call_id"] == "process-f1"
    assert observed["args_sha256"] == logical["args_sha256"] == digest(context)
    assert observed["http_status"] == status and observed["code"] == code
    assert observed["response_state"] == "prepared" and observed["finished_at"] is not None
    assert observed["client_received"] is None
    assert [phase["phase"] for phase in observed["phases"]] == [
        "started",
        "completed" if status == 200 else "failed",
    ]
    assert all(phase["artifact_id"] is None for phase in observed["phases"])


def test_process_retry_after_synthetic_repair_has_two_physical_attempts_one_logical_id(
    client, context, corpus, engine
):
    service = client.app.state.execution
    service.max_tool_calls = 1
    scope = (
        processes.c.process_id == context["process_id"],
        processes.c.corpus_version == context["corpus_version"],
    )
    original = corpus[0].model_dump(mode="json")
    with engine.begin() as conn:
        conn.execute(update(processes).where(*scope).values(payload=None))
    headers = {"X-Tool-Call-Id": "recover-process"}
    first = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert first.status_code == 500 and first.json()["code"] == "invalid_response"
    with engine.begin() as conn:
        conn.execute(update(processes).where(*scope).values(payload=original))
    second = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert second.status_code == 200
    with engine.connect() as conn:
        physical = service.tracking.history(conn, context["run_id"])
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert len(physical) == 2 and len({row["attempt_id"] for row in physical}) == 2
    assert {row["http_status"] for row in physical} == {200, 500}
    assert all(
        row["tool_call_id"] == logical["tool_call_id"] == "recover-process" for row in physical
    )
    assert all(row["args_sha256"] == logical["args_sha256"] for row in physical)
    assert all(row["client_received"] is None and len(row["phases"]) == 2 for row in physical)
    assert not any(p["phase"] == "effect_confirmed" for row in physical for p in row["phases"])

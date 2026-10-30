"""F4: checklist outcomes, version isolation and physical tracking."""

import httpx
import pytest
from sqlalchemy import delete, event, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import tool_outcome
from services.backend.execution import digest
from services.backend.schema import artifacts, logical_tool_calls, requirements
from tests.backend.test_tool_calls import write_body


def scope(context):
    return tuple(
        getattr(requirements.c, key) == context[key]
        for key in ("process_id", "corpus_version", "requirements_version")
    )


@pytest.mark.parametrize(
    ("scenario", "status", "code"),
    [
        ("normal", 200, None),
        ("absent", 404, "not_found"),
        ("null", 500, "invalid_response"),
        ("identity", 500, "invalid_response"),
        ("duplicate", 500, "invalid_response"),
        ("storage", 503, "storage_unavailable"),
    ],
)
def test_checklist_outcome_matches_reservation_and_physical_request(
    client, context, engine, scenario, status, code
):
    with engine.begin() as conn:
        if scenario == "absent":
            conn.execute(delete(requirements).where(*scope(context)))
        elif scenario in {"null", "identity", "duplicate"}:
            payload = conn.execute(
                select(requirements.c.payload).where(*scope(context))
            ).scalar_one()
            if scenario == "null":
                payload = None
            elif scenario == "identity":
                payload["requirement_id"] = "SYNTHETIC-PRIVATE-OTHER"
            if scenario == "duplicate":
                conn.execute(
                    insert(requirements).values(
                        **{
                            k: context[k]
                            for k in ("process_id", "corpus_version", "requirements_version")
                        },
                        requirement_id="OTHER-KEY",
                        payload=payload,
                    )
                )
            else:
                conn.execute(update(requirements).where(*scope(context)).values(payload=payload))

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM requirements" in statement:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-SQL")

    if scenario == "storage":
        event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post(
            "/tools/consultar_requisitos", headers={"X-Tool-Call-Id": "checklist-f4"}, json=context
        )
    finally:
        if scenario == "storage":
            event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == status and "SYNTHETIC-PRIVATE" not in response.text
    if status == 200:
        parsed = tool_outcome(
            httpx.Response(
                200,
                json=response.json(),
                request=httpx.Request("POST", "http://test/tools/consultar_requisitos"),
            ),
            "consultar_requisitos",
            context,
            context,
        )
        assert parsed == response.json()
        assert [v["requirement_id"] for v in parsed["items"]] == ["REQ-DEMO-001"]
        assert len({v["requirement_id"] for v in parsed["items"]}) == len(parsed["items"])
    else:
        assert response.json()["code"] == code and response.json()["retryable"] is (status == 503)
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
    row = physical[0]
    assert row["tool"] == logical["tool"] == "consultar_requisitos"
    assert row["tool_call_id"] == logical["tool_call_id"] == "checklist-f4"
    assert row["args_sha256"] == logical["args_sha256"] == digest(context)
    assert row["http_status"] == status and row["code"] == code
    assert row["response_state"] == "prepared" and row["client_received"] is None
    assert [p["phase"] for p in row["phases"]] == [
        "started",
        "completed" if status == 200 else "failed",
    ]
    assert all(p["artifact_id"] is None for p in row["phases"])


def test_versioned_checklist_to_pendency_rejects_foreign_requirement(
    client, context, corpus, engine
):
    keys = ("process_id", "corpus_version", "requirements_version")
    with engine.begin() as conn:
        for field in keys:
            foreign = {k: context[k] for k in keys}
            foreign[field] = "OTHER"
            conn.execute(
                insert(requirements).values(
                    **foreign,
                    requirement_id="FOREIGN-REQ",
                    payload={
                        "requirement_id": "FOREIGN-REQ",
                        "description": "Synthetic foreign",
                        "source": "Synthetic",
                    },
                )
            )
    listed = client.post(
        "/tools/consultar_requisitos", headers={"X-Tool-Call-Id": "list-checklist"}, json=context
    )
    assert listed.status_code == 200
    assert [v["requirement_id"] for v in listed.json()["items"]] == ["REQ-DEMO-001"]
    body = write_body(context, corpus)
    bad = client.post(
        "/tools/registrar_pendencia",
        headers={"X-Tool-Call-Id": "foreign-write"},
        json={**body, "requirement_id": "FOREIGN-REQ"},
    )
    assert bad.status_code == 422 and bad.json()["code"] == "validation_error"
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )
    selected = listed.json()["items"][0]["requirement_id"]
    written = client.post(
        "/tools/registrar_pendencia",
        headers={"X-Tool-Call-Id": "valid-write"},
        json={**body, "requirement_id": selected},
    )
    assert written.status_code == 200
    item = client.get(
        f"/artifacts/{written.json()['artifact_id']}", headers=client.operator_headers
    )
    assert item.status_code == 200 and item.json()["payload"]["requirement_id"] == selected
    assert item.json()["receipt"] == written.json()
    with engine.connect() as conn:
        physical = client.app.state.execution.tracking.history(conn, context["run_id"])
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    by_id = {r["tool_call_id"]: r for r in physical}
    assert len(by_id) == 3 and len({r["attempt_id"] for r in physical}) == 3
    assert [p["phase"] for p in by_id["list-checklist"]["phases"]] == ["started", "completed"]
    assert [p["phase"] for p in by_id["foreign-write"]["phases"]] == ["started", "failed"]
    assert [p["phase"] for p in by_id["valid-write"]["phases"]] == [
        "started",
        "effect_confirmed",
        "completed",
    ]
    assert by_id["valid-write"]["phases"][1]["artifact_id"] == written.json()["artifact_id"]

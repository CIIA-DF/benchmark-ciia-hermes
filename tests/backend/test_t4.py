"""Integrated acceptance for versioned checklist reads and their consumers."""

from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, event, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import ToolCallError, tool_outcome, transient
from scripts.checklist import import_checklist
from services.backend.schema import artifacts, logical_tool_calls, requirements
from tests.backend.test_tool_calls import history, write_body


def scope(context):
    return (
        requirements.c.process_id == context["process_id"],
        requirements.c.corpus_version == context["corpus_version"],
        requirements.c.requirements_version == context["requirements_version"],
    )


def checklist(client, context):
    return client.post("/tools/consultar_requisitos", json=context)


def test_import_is_immutable_and_checklist_feeds_pendency(client, corpus, context, engine):
    items = [
        {
            "requirement_id": name,
            "description": "Synthetic requirement",
            "source": "Synthetic checklist",
        }
        for name in ("REQ-B", "REQ-A")
    ]
    with engine.begin() as conn:
        conn.execute(delete(requirements).where(*scope(context)))
    params = (
        engine,
        context["process_id"],
        context["corpus_version"],
        context["requirements_version"],
    )
    import_checklist(*params, items)
    first = checklist(client, context)
    assert first.status_code == 200
    assert [item["requirement_id"] for item in first.json()["items"]] == ["REQ-A", "REQ-B"]
    import_checklist(*params, list(reversed(items)))
    assert checklist(client, context).json() == first.json()
    changed = deepcopy(items)
    changed[0]["description"] = "Changed"
    with pytest.raises(ValueError, match="imutável"):
        import_checklist(*params, changed)
    assert checklist(client, context).json() == first.json()
    selected = first.json()["items"][0]["requirement_id"]
    body = {
        **write_body(context, corpus, content="Pendencia sintetica"),
        "requirement_id": selected,
    }
    written = client.post("/tools/registrar_pendencia", json=body)
    assert written.status_code == 200
    artifact = client.get(
        f"/artifacts/{written.json()['artifact_id']}", headers=client.operator_headers
    )
    assert artifact.status_code == 200
    assert artifact.json()["payload"]["requirement_id"] == selected
    assert artifact.json()["receipt"]["artifact_id"] == written.json()["artifact_id"]


def test_scope_filters_process_corpus_and_version_before_returning_ids(
    client, corpus, context, engine
):
    with engine.begin() as conn:
        for field in ("process_id", "corpus_version", "requirements_version"):
            foreign = {
                key: context[key]
                for key in ("process_id", "corpus_version", "requirements_version")
            }
            foreign[field] = "OTHER"
            conn.execute(
                insert(requirements).values(
                    **foreign,
                    requirement_id="AAA-FOREIGN",
                    payload={
                        "requirement_id": "AAA-FOREIGN",
                        "description": "Foreign synthetic",
                        "source": "Other checklist",
                    },
                )
            )
    result = checklist(client, context)
    assert result.status_code == 200
    assert [i["requirement_id"] for i in result.json()["items"]] == ["REQ-DEMO-001"]
    assert result.json()["requirements_version"] == context["requirements_version"]
    bad = client.post(
        "/tools/registrar_pendencia",
        json={**write_body(context, corpus), "requirement_id": "AAA-FOREIGN"},
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


@pytest.mark.parametrize(
    "corruption",
    ["identity", "missing_description", "empty_source", "list", "null", "duplicate_payload"],
)
def test_corrupt_checklist_is_safe_audited_and_keeps_reservation(
    client, context, engine, corruption
):
    payload = {
        "requirement_id": "REQ-DEMO-001",
        "description": "SYNTHETIC-PRIVATE-CHECKLIST",
        "source": "Synthetic",
    }
    if corruption == "identity":
        payload["requirement_id"] = "SYNTHETIC-PRIVATE-ID"
    elif corruption == "missing_description":
        payload.pop("description")
    elif corruption == "empty_source":
        payload["source"] = " "
    elif corruption == "list":
        payload = ["SYNTHETIC-PRIVATE-CHECKLIST"]
    elif corruption == "null":
        payload = None
    with engine.begin() as conn:
        if corruption == "duplicate_payload":
            conn.execute(
                insert(requirements).values(
                    **{
                        key: context[key]
                        for key in ("process_id", "corpus_version", "requirements_version")
                    },
                    requirement_id="ZZ-SECOND",
                    payload=payload,
                )
            )
        else:
            conn.execute(update(requirements).where(*scope(context)).values(payload=payload))
    result = checklist(client, context)
    assert result.status_code == 500 and result.json()["code"] == "invalid_response"
    assert result.json()["retryable"] is False and "SYNTHETIC-PRIVATE" not in result.text
    attempts = history(client, engine, context["run_id"])
    assert len(attempts) == 1 and attempts[0]["code"] == "invalid_response"
    assert attempts[0]["http_status"] == 500
    with engine.connect() as conn:
        binding = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert binding["args_sha256"] == attempts[0]["args_sha256"]


def test_absent_checklist_is_404_and_invalid_scope_is_403(client, context, engine):
    mismatch = client.post(
        "/tools/consultar_requisitos", json={**context, "requirements_version": "OTHER"}
    )
    assert mismatch.status_code == 403
    with engine.begin() as conn:
        conn.execute(delete(requirements).where(*scope(context)))
    missing = checklist(client, context)
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"


def test_database_query_failure_is_503_with_safe_audit(client, context, engine):
    def broken(conn, cursor, statement, parameters, execution_context, executemany):
        if "FROM requirements" in statement:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-SQL")

    event.listen(engine, "before_cursor_execute", broken)
    try:
        response = checklist(client, context)
    finally:
        event.remove(engine, "before_cursor_execute", broken)
    assert response.status_code == 503 and response.json()["retryable"]
    assert "SYNTHETIC-PRIVATE" not in response.text
    assert history(client, engine, context["run_id"])[0]["code"] == "storage_unavailable"


def test_client_rejects_duplicate_empty_invalid_and_foreign_checklists(client, context):
    good = checklist(client, context).json()
    variants = [
        {**good, "items": []},
        {**good, "items": good["items"] * 2},
        {**good, "items": [None]},
    ]
    invalid_item = deepcopy(good)
    invalid_item["items"][0].pop("source")
    variants.append(invalid_item)
    for field in ("run_id", "process_id", "corpus_version", "requirements_version"):
        other = deepcopy(good)
        other[field] = str(uuid4()) if field == "run_id" else "OTHER"
        variants.append(other)
    for value in variants:
        with pytest.raises(ToolCallError) as error:
            tool_outcome(
                httpx.Response(
                    200,
                    json=value,
                    request=httpx.Request("POST", "http://test/tools/consultar_requisitos"),
                ),
                "consultar_requisitos",
                context,
                context,
            )
        assert not transient(error.value)
    parsed = tool_outcome(
        httpx.Response(
            200, json=good, request=httpx.Request("POST", "http://test/tools/consultar_requisitos")
        ),
        "consultar_requisitos",
        context,
        context,
    )
    assert parsed == good

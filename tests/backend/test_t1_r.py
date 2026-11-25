"""Integrated regressions for malformed stored process metadata and auditing."""

from copy import deepcopy

import pytest
from sqlalchemy import delete, func, select, update

from services.backend.schema import artifacts, logical_tool_calls
from services.backend.storage import chunks, documents, processes
from tests.backend.test_tool_calls import history, write_body


@pytest.mark.parametrize(
    "corruption",
    [
        "missing_version",
        "invalid_version",
        "foreign_process",
        "foreign_corpus",
        "list",
        "string",
        "null",
    ],
)
def test_invalid_process_is_safe_audited_and_retryable_only_after_repair(
    client, corpus, context, engine, corruption
):
    client.app.state.execution.max_tool_calls = 1
    process, _ = corpus
    original = process.model_dump(mode="json")
    payload = deepcopy(original)
    payload["export_note"] = "SYNTHETIC-PRIVATE-METADATA"
    if corruption == "missing_version":
        payload.pop("requirements_version")
    elif corruption == "invalid_version":
        payload["requirements_version"] = None
    elif corruption == "foreign_process":
        payload["process_id"] = "SYNTHETIC-PRIVATE-PROCESS"
    elif corruption == "foreign_corpus":
        payload["corpus_version"] = "SYNTHETIC-PRIVATE-CORPUS"
    elif corruption == "list":
        payload = ["SYNTHETIC-PRIVATE-METADATA"]
    elif corruption == "string":
        payload = "SYNTHETIC-PRIVATE-METADATA"
    else:
        payload = None
    where = (
        processes.c.process_id == context["process_id"],
        processes.c.corpus_version == context["corpus_version"],
    )
    with engine.begin() as conn:
        conn.execute(update(processes).where(*where).values(payload=payload))
    headers = {"X-Tool-Call-Id": "invalid-process"}
    response = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "invalid_response"
    assert response.json()["retryable"] is False
    assert "SYNTHETIC-PRIVATE" not in response.text
    assert "requirements_version" not in response.text
    with engine.connect() as conn:
        reserved = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    attempts = history(client, engine, context["run_id"])
    assert len(attempts) == 1 and attempts[0]["http_status"] == 500
    assert attempts[0]["code"] == "invalid_response"
    assert attempts[0]["args_sha256"] == reserved["args_sha256"]
    assert reserved["tool_call_id"] == "invalid-process"
    with engine.begin() as conn:
        conn.execute(update(processes).where(*where).values(payload=original))
    repaired = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert repaired.status_code == 200 and repaired.json()["process"] == original
    assert [a["http_status"] for a in history(client, engine, context["run_id"])] == [500, 200]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(logical_tool_calls)
                .where(logical_tool_calls.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )


def test_missing_version_is_audited_for_all_tools_without_artifacts(
    client, corpus, context, engine
):
    client.app.state.execution.max_tool_calls = 6
    original = corpus[0].model_dump(mode="json")
    invalid = {k: v for k, v in original.items() if k != "requirements_version"}
    with engine.begin() as conn:
        conn.execute(
            update(processes)
            .where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
            .values(payload=invalid)
        )
    calls = [
        ("consultar_processo", context),
        ("buscar_documentos", {**context, "query": "material"}),
        ("ler_documento", {**context, "document_id": corpus[1].document_id}),
        ("consultar_requisitos", context),
        ("registrar_pendencia", {**write_body(context, corpus), "requirement_id": "REQ-DEMO-001"}),
        ("salvar_minuta", write_body(context, corpus)),
    ]
    paths = client.get("/openapi.json").json()["paths"]
    for tool, body in calls:
        assert paths[f"/tools/{tool}"]["post"]["responses"]["500"]["content"]["application/json"][
            "schema"
        ]["$ref"].endswith("/ToolError")
        response = client.post(f"/tools/{tool}", headers={"X-Tool-Call-Id": tool}, json=body)
        assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    attempts = history(client, engine, context["run_id"])
    assert len(attempts) == 6 and all(a["code"] == "invalid_response" for a in attempts)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )


def test_valid_version_conflict_absence_and_empty_inventory_stay_distinct(
    client, corpus, context, engine
):
    original = corpus[0].model_dump(mode="json")
    where = (
        processes.c.process_id == context["process_id"],
        processes.c.corpus_version == context["corpus_version"],
    )
    with engine.begin() as conn:
        conn.execute(
            update(processes)
            .where(*where)
            .values(payload={**original, "requirements_version": "OTHER"})
        )
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 409 and result.json()["code"] == "version_mismatch"
    with engine.begin() as conn:
        conn.execute(update(processes).where(*where).values(payload=original))
        for table in (chunks, documents):
            conn.execute(
                delete(table).where(
                    table.c.process_id == context["process_id"],
                    table.c.corpus_version == context["corpus_version"],
                )
            )
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 200 and result.json()["inventory"] == []
    with engine.begin() as conn:
        conn.execute(delete(processes).where(*where))
    result = client.post("/tools/consultar_processo", json=context)
    assert result.status_code == 404 and result.json()["code"] == "not_found"

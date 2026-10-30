"""HTTP acceptance for pendency integrity, durable effects and consumer receipts."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import ToolCallError, tool_outcome, transient
from contracts.models import PendencyInput
from services.backend.execution import digest
from services.backend.schema import artifacts, logical_tool_calls, requirements
from services.backend.storage import chunks
from tests.backend.test_tool_calls import history, write_body


def body_for(context, corpus):
    return {**write_body(context, corpus), "requirement_id": "REQ-DEMO-001"}


def write(client, body, call_id="pendency"):
    return client.post("/tools/registrar_pendencia", headers={"X-Tool-Call-Id": call_id}, json=body)


def artifact_count(engine, context):
    with engine.connect() as conn:
        return conn.execute(
            select(func.count())
            .select_from(artifacts)
            .where(artifacts.c.run_id == context["run_id"])
        ).scalar_one()


def requirement_scope(context):
    return (
        requirements.c.process_id == context["process_id"],
        requirements.c.corpus_version == context["corpus_version"],
        requirements.c.requirements_version == context["requirements_version"],
    )


def evidence_body(client, context, corpus):
    result = client.post("/tools/buscar_documentos", json={**context, "query": "material"})
    assert result.status_code == 200 and result.json()["items"]
    chunk = result.json()["items"][0]
    ref = {key: chunk[key] for key in ("document_id", "chunk_id", "page")}
    return {**body_for(context, corpus), "evidence": [ref]}


def test_checklist_search_to_confirmed_pendency_with_independent_hash(
    client, context, corpus, engine
):
    listed = client.post("/tools/consultar_requisitos", json=context).json()
    body = evidence_body(client, context, corpus)
    body["requirement_id"] = listed["items"][0]["requirement_id"]
    body["content"] = "  Pendência sintética com acentuação.  "
    body["evidence"].append(write_body(context, corpus)["evidence"][0])
    normalized = PendencyInput.model_validate(body).model_dump(mode="json")
    response = write(client, body)
    assert response.status_code == 200 and not response.json()["replayed"]
    receipt = response.json()
    stored = client.get(f"/artifacts/{receipt['artifact_id']}", headers=client.operator_headers)
    assert stored.status_code == 200
    assert stored.json()["tool"] == "registrar_pendencia"
    assert stored.json()["payload"] == normalized
    assert stored.json()["receipt"] == receipt
    assert receipt["content_sha256"] == hashlib.sha256(normalized["content"].encode()).hexdigest()
    assert artifact_count(engine, context) == 1
    with engine.connect() as conn:
        row = (
            conn.execute(select(artifacts).where(artifacts.c.artifact_id == receipt["artifact_id"]))
            .mappings()
            .one()
        )
        assert row["input_sha256"] == digest(normalized)
    repeated = write(client, body)
    assert repeated.status_code == 200
    assert repeated.json() == {**receipt, "replayed": True}
    assert [r["replayed"] for r in history(client, engine, context["run_id"])[-2:]] == [False, True]


@pytest.mark.parametrize("invalid", ["requirement", "chunk", "page", "inventory", "empty"])
def test_invalid_requirement_or_evidence_has_no_effect(client, context, corpus, engine, invalid):
    body = body_for(context, corpus)
    if invalid == "requirement":
        body["requirement_id"] = "NOT-IN-THIS-VERSION"
    elif invalid == "chunk":
        body["evidence"] = [{"document_id": "other", "chunk_id": "other", "page": 1}]
    elif invalid == "page":
        body = evidence_body(client, context, corpus)
        body["evidence"][0]["page"] += 1000
    elif invalid == "inventory":
        body["evidence"][0]["process_id"] = "OTHER"
    else:
        body["evidence"] = []
    response = write(client, body)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["http_status"] == 422
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(logical_tool_calls).where(
                    logical_tool_calls.c.run_id == context["run_id"],
                    logical_tool_calls.c.tool_call_id == "pendency",
                )
            ).first()
            is not None
        )


@pytest.mark.parametrize("corruption", ["null", "missing", "identity"])
def test_corrupt_selected_requirement_is_safe_audited(client, context, corpus, engine, corruption):
    with engine.begin() as conn:
        payload = conn.execute(
            select(requirements.c.payload).where(*requirement_scope(context))
        ).scalar_one()
        if corruption == "null":
            payload = None
        elif corruption == "missing":
            payload.pop("description")
        else:
            payload["requirement_id"] = "SYNTHETIC-PRIVATE-OTHER"
        conn.execute(
            update(requirements).where(*requirement_scope(context)).values(payload=payload)
        )
    response = write(client, body_for(context, corpus))
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert not response.json()["retryable"] and "SYNTHETIC-PRIVATE" not in response.text
    assert artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["code"] == "invalid_response"


@pytest.mark.parametrize("corruption", ["null", "page", "scope"])
def test_corrupt_referenced_chunk_is_safe_audited(client, context, corpus, engine, corruption):
    body = evidence_body(client, context, corpus)
    ref = body["evidence"][0]
    scope = (
        chunks.c.chunk_id == ref["chunk_id"],
        chunks.c.process_id == context["process_id"],
        chunks.c.corpus_version == context["corpus_version"],
    )
    with engine.begin() as conn:
        payload = conn.execute(select(chunks.c.payload).where(*scope)).scalar_one()
        if corruption == "null":
            payload = None
        elif corruption == "page":
            payload.pop("page")
        else:
            payload["process_id"] = "SYNTHETIC-PRIVATE-OTHER"
        conn.execute(update(chunks).where(*scope).values(payload=payload))
    response = write(client, body)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert "SYNTHETIC-PRIVATE" not in response.text
    assert artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["http_status"] == 500


def test_concurrent_same_key_replays_once_and_changed_input_conflicts(
    client, context, corpus, engine
):
    body = body_for(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda i: write(client, body, f"parallel-{i}"), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()["replayed"] for r in responses) == [False, True]
    assert len({r.json()["artifact_id"] for r in responses}) == 1
    conflict = write(client, {**body, "content": "Changed synthetic"}, "changed")
    assert conflict.status_code == 409 and conflict.json()["code"] == "idempotency_conflict"
    assert artifact_count(engine, context) == 1


def test_failure_after_insert_rolls_back_then_same_identity_recovers(
    client, context, corpus, engine, monkeypatch
):
    service = client.app.state.execution
    original = service.tool_attempt

    def fail_success(conn, run_id, call, status, **kwargs):
        if status == 200:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-ROLLBACK")
        return original(conn, run_id, call, status, **kwargs)

    monkeypatch.setattr(service, "tool_attempt", fail_success)
    body = body_for(context, corpus)
    response = write(client, body)
    assert response.status_code == 503 and response.json()["retryable"]
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["code"] == "storage_unavailable"
    monkeypatch.setattr(service, "tool_attempt", original)
    assert write(client, body).status_code == 200
    assert artifact_count(engine, context) == 1


@pytest.mark.parametrize(
    "corruption",
    [
        "null",
        "context",
        "hash",
        "id",
        "date",
        "replayed",
        "payload",
        "payload_whitespace",
        "input_hash",
    ],
)
def test_corrupt_stored_artifact_is_not_successfully_replayed(
    client, context, corpus, engine, corruption
):
    body = body_for(context, corpus)
    first = write(client, body)
    assert first.status_code == 200
    key = first.json()["artifact_id"]
    with engine.begin() as conn:
        row = conn.execute(select(artifacts).where(artifacts.c.artifact_id == key)).mappings().one()
        receipt = deepcopy(row["receipt"])
        change = {}
        if corruption == "null":
            receipt = None
        elif corruption == "context":
            receipt["process_id"] = "SYNTHETIC-PRIVATE-OTHER"
        elif corruption == "hash":
            receipt["content_sha256"] = "0" * 64
        elif corruption == "id":
            receipt["artifact_id"] = str(uuid4())
        elif corruption == "date":
            receipt["persisted_at"] = "2026-10-29T10:00:00"
        elif corruption == "replayed":
            receipt["replayed"] = True
        elif corruption == "payload":
            change["payload"] = {**row["payload"], "requirement_id": "OTHER"}
        elif corruption == "payload_whitespace":
            change["payload"] = {**row["payload"], "content": "  " + row["payload"]["content"]}
        else:
            change["input_sha256"] = "0" * 64
        change["receipt"] = receipt
        conn.execute(update(artifacts).where(artifacts.c.artifact_id == key).values(**change))
    response = write(client, body)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert "SYNTHETIC-PRIVATE" not in response.text and not response.json()["retryable"]
    assert artifact_count(engine, context) == 1
    assert history(client, engine, context["run_id"])[-1]["code"] == "invalid_response"


def test_persisted_content_changed_before_commit_is_rolled_back(client, context, corpus, engine):
    def tampered(conn, cursor, statement, params, exec_context, many):
        if statement.startswith("INSERT INTO artifacts"):
            row = (
                conn.execute(select(artifacts).where(artifacts.c.run_id == context["run_id"]))
                .mappings()
                .one()
            )
            payload = {**row["payload"], "content": "SYNTHETIC-PRIVATE-REWRITE"}
            receipt = {
                **row["receipt"],
                "content_sha256": hashlib.sha256(payload["content"].encode()).hexdigest(),
            }
            conn.execute(
                update(artifacts)
                .where(artifacts.c.artifact_id == row["artifact_id"])
                .values(payload=payload, input_sha256=digest(payload), receipt=receipt)
            )

    event.listen(engine, "after_cursor_execute", tampered)
    try:
        response = write(client, body_for(context, corpus))
    finally:
        event.remove(engine, "after_cursor_execute", tampered)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["http_status"] == 500


def test_failure_of_independent_post_commit_read_recovers_by_replay(
    client, context, corpus, engine
):
    reads = []

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM artifacts" in statement:
            reads.append(statement)
            if len(reads) == 3:
                raise SQLAlchemyError("SYNTHETIC-PRIVATE-POSTCOMMIT")

    body = body_for(context, corpus)
    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = write(client, body)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503 and response.json()["retryable"]
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 1
    repeated = write(client, body)
    assert repeated.status_code == 200 and repeated.json()["replayed"]
    assert artifact_count(engine, context) == 1
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [200, 503, 200]


def test_client_rejects_foreign_or_false_receipt_without_echo(client, context, corpus):
    body = body_for(context, corpus)
    good = write(client, body).json()
    variants = [
        {**good, "content_sha256": "0" * 64},
        {**good, "artifact_id": "bad"},
        {**good, "persisted_at": "2026-10-29T10:00:00"},
    ]
    for field in ("run_id", "process_id", "corpus_version", "requirements_version"):
        variants.append(
            {**good, field: str(uuid4()) if field == "run_id" else "SYNTHETIC-PRIVATE-OTHER"}
        )
    for value in variants:
        response = httpx.Response(
            200, json=value, request=httpx.Request("POST", "http://test/tools/registrar_pendencia")
        )
        with pytest.raises(ToolCallError) as error:
            tool_outcome(response, "registrar_pendencia", context, body)
        assert not transient(error.value) and "SYNTHETIC-PRIVATE" not in str(error.value)
    assert (
        tool_outcome(
            httpx.Response(
                200,
                json=good,
                request=httpx.Request("POST", "http://test/tools/registrar_pendencia"),
            ),
            "registrar_pendencia",
            context,
            body,
        )
        == good
    )


def test_shared_source_validation_keeps_run_result_atomic(client, context, corpus, engine):
    body = evidence_body(client, context, corpus)
    with engine.begin() as conn:
        conn.execute(
            update(chunks)
            .where(
                chunks.c.chunk_id == body["evidence"][0]["chunk_id"],
                chunks.c.process_id == context["process_id"],
                chunks.c.corpus_version == context["corpus_version"],
            )
            .values(payload=None)
        )
    response = client.post(
        f"/runs/{context['run_id']}/result",
        json={
            "status": "failed",
            "error_code": "adapter_error",
            "sources": body["evidence"],
        },
    )
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    state = client.get(f"/runs/{context['run_id']}", headers=client.operator_headers)
    assert state.status_code == 200 and state.json()["status"] == "running"

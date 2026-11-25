"""HTTP acceptance for draft integrity and both consumer paths."""

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import AsyncToolClient, ToolCallError, ToolClient, tool_outcome, transient
from contracts.execution import ClaimedRun
from contracts.models import WriteInput
from services.backend.execution import digest
from services.backend.schema import artifacts, requirements
from services.backend.storage import chunks
from tests.backend.test_t5 import artifact_count
from tests.backend.test_tool_calls import history, write_body


def write(client, body, call_id="draft"):
    return client.post("/tools/salvar_minuta", headers={"X-Tool-Call-Id": call_id}, json=body)


def evidence_body(client, context, corpus):
    searched = client.post("/tools/buscar_documentos", json={**context, "query": "material"})
    assert searched.status_code == 200 and searched.json()["items"]
    chunk = searched.json()["items"][0]
    ref = {key: chunk[key] for key in ("document_id", "chunk_id", "page")}
    return {**write_body(context, corpus), "evidence": [ref]}


def test_search_read_to_draft_without_checklist_or_pendency(client, context, corpus, engine):
    with engine.begin() as conn:
        conn.execute(
            delete(requirements).where(
                requirements.c.process_id == context["process_id"],
                requirements.c.corpus_version == context["corpus_version"],
                requirements.c.requirements_version == context["requirements_version"],
            )
        )
    body = evidence_body(client, context, corpus)
    ref = body["evidence"][0]
    read = client.post(
        "/tools/ler_documento",
        json={**context, "document_id": ref["document_id"], "pages": [ref["page"]]},
    )
    assert read.status_code == 200 and read.json()["document"]["pages"][0]["text"]
    body["evidence"].append(write_body(context, corpus)["evidence"][0])
    body["content"] = "  Minuta sintética com acentuação.  "
    normalized = WriteInput.model_validate(body).model_dump(mode="json")
    first = write(client, body)
    assert first.status_code == 200 and not first.json()["replayed"]
    receipt = first.json()
    stored = client.get(f"/artifacts/{receipt['artifact_id']}", headers=client.operator_headers)
    assert stored.status_code == 200 and stored.json()["tool"] == "salvar_minuta"
    assert stored.json()["payload"] == normalized and "requirement_id" not in normalized
    assert stored.json()["receipt"] == receipt
    assert receipt["content_sha256"] == hashlib.sha256(normalized["content"].encode()).hexdigest()
    with engine.connect() as conn:
        assert conn.execute(
            select(artifacts.c.input_sha256).where(
                artifacts.c.artifact_id == receipt["artifact_id"]
            )
        ).scalar_one() == digest(normalized)
    repeated = write(client, body)
    assert repeated.status_code == 200 and repeated.json() == {**receipt, "replayed": True}
    assert artifact_count(engine, context) == 1


@pytest.mark.parametrize("invalid", ["empty", "chunk", "page", "inventory", "requirement_field"])
def test_invalid_draft_has_no_effect_and_is_audited(client, context, corpus, engine, invalid):
    body = write_body(context, corpus)
    if invalid == "empty":
        body["evidence"] = []
    elif invalid == "chunk":
        body["evidence"] = [{"document_id": "OTHER", "chunk_id": "OTHER", "page": 1}]
    elif invalid == "page":
        body = evidence_body(client, context, corpus)
        body["evidence"][0]["page"] += 1000
    elif invalid == "inventory":
        body["evidence"][0]["corpus_version"] = "OTHER"
    else:
        body["requirement_id"] = "REQ-DEMO-001"
    response = write(client, body)
    assert response.status_code == 422 and response.json()["code"] == "validation_error"
    assert artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["http_status"] == 422


@pytest.mark.parametrize("corruption", ["null", "identity"])
def test_corrupt_draft_source_is_safe_and_audited(client, context, corpus, engine, corruption):
    body = evidence_body(client, context, corpus)
    scope = (
        chunks.c.chunk_id == body["evidence"][0]["chunk_id"],
        chunks.c.process_id == context["process_id"],
        chunks.c.corpus_version == context["corpus_version"],
    )
    with engine.begin() as conn:
        payload = conn.execute(select(chunks.c.payload).where(*scope)).scalar_one()
        if corruption == "null":
            payload = None
        else:
            payload["document_id"] = "SYNTHETIC-PRIVATE-OTHER"
        conn.execute(update(chunks).where(*scope).values(payload=payload))
    response = write(client, body)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert not response.json()["retryable"] and "SYNTHETIC-PRIVATE" not in response.text
    assert artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["code"] == "invalid_response"


def test_budget_one_keeps_identity_and_recovers_original_receipt(client, context, corpus, engine):
    client.app.state.execution.max_tool_calls = 1
    body = write_body(context, corpus)
    first = write(client, body)
    changed = {**body, "content": "Changed synthetic", "idempotency_key": "second"}
    mismatch = write(client, changed)
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "idempotency_conflict"
    exhausted = write(client, changed, "new-call")
    assert exhausted.status_code == 409 and exhausted.json()["code"] == "budget_exceeded"
    recovered = write(client, body)
    assert first.status_code == recovered.status_code == 200
    assert recovered.json() == {**first.json(), "replayed": True}
    assert artifact_count(engine, context) == 1
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [
        200,
        409,
        409,
        200,
    ]


def test_concurrent_same_key_confirms_only_one_draft(client, context, corpus, engine):
    body = write_body(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda i: write(client, body, f"parallel-{i}"), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert sorted(r.json()["replayed"] for r in responses) == [False, True]
    assert len({r.json()["artifact_id"] for r in responses}) == 1
    changed = write(client, {**body, "content": "Changed synthetic"}, "changed")
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    assert artifact_count(engine, context) == 1


@pytest.mark.parametrize("corruption", ["context", "id", "payload"])
def test_corrupt_persisted_draft_does_not_replay(client, context, corpus, engine, corruption):
    body = write_body(context, corpus)
    first = write(client, body)
    assert first.status_code == 200
    key = first.json()["artifact_id"]
    with engine.begin() as conn:
        row = conn.execute(select(artifacts).where(artifacts.c.artifact_id == key)).mappings().one()
        receipt = deepcopy(row["receipt"])
        change = {}
        if corruption == "context":
            receipt["requirements_version"] = "SYNTHETIC-PRIVATE-OTHER"
        elif corruption == "id":
            receipt["artifact_id"] = str(uuid4())
        else:
            change["payload"] = {**row["payload"], "content": "SYNTHETIC-PRIVATE-OTHER"}
        conn.execute(
            update(artifacts)
            .where(artifacts.c.artifact_id == key)
            .values(receipt=receipt, **change)
        )
    response = write(client, body)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 1
    assert history(client, engine, context["run_id"])[-1]["http_status"] == 500


def test_draft_rollback_preserves_reservation_and_recovers(
    client, context, corpus, engine, monkeypatch
):
    service = client.app.state.execution
    original = service.tool_attempt

    def broken(conn, run_id, call, status, **kwargs):
        if status == 200:
            raise SQLAlchemyError("SYNTHETIC-PRIVATE-ROLLBACK")
        return original(conn, run_id, call, status, **kwargs)

    body = write_body(context, corpus)
    monkeypatch.setattr(service, "tool_attempt", broken)
    response = write(client, body)
    assert response.status_code == 503 and response.json()["retryable"]
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 0
    monkeypatch.setattr(service, "tool_attempt", original)
    recovered = write(client, body)
    assert recovered.status_code == 200 and not recovered.json()["replayed"]
    assert artifact_count(engine, context) == 1
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [503, 200]


def test_rewritten_draft_before_commit_is_rolled_back(client, context, corpus, engine):
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
        response = write(client, write_body(context, corpus))
    finally:
        event.remove(engine, "after_cursor_execute", tampered)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 0
    assert history(client, engine, context["run_id"])[-1]["code"] == "invalid_response"


def test_post_commit_read_failure_keeps_effect_and_retry_replays(client, context, corpus, engine):
    reads = []

    def unavailable(conn, cursor, statement, params, exec_context, many):
        if "FROM artifacts" in statement:
            reads.append(statement)
            if len(reads) == 3:
                raise SQLAlchemyError("SYNTHETIC-PRIVATE-POSTCOMMIT")

    body = write_body(context, corpus)
    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = write(client, body)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503 and response.json()["retryable"]
    assert "SYNTHETIC-PRIVATE" not in response.text and artifact_count(engine, context) == 1
    recovered = write(client, body)
    assert recovered.status_code == 200 and recovered.json()["replayed"]
    assert artifact_count(engine, context) == 1
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [200, 503, 200]


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("corruption", ["context", "hash"])
def test_both_clients_reject_forged_draft_receipt_without_retry(
    client, context, corpus, engine, asynchronous, corruption
):
    body = write_body(context, corpus)
    arguments = {key: value for key, value in body.items() if key not in context}
    seen = []

    def respond(request):
        seen.append(request.content)
        response = client.post(
            request.url.path, headers=dict(request.headers), json=json.loads(request.content)
        )
        assert response.status_code == 200
        receipt = response.json()
        if corruption == "context":
            receipt["process_id"] = "SYNTHETIC-PRIVATE-OTHER"
        else:
            receipt["content_sha256"] = "0" * 64
        return httpx.Response(200, json=receipt)

    if asynchronous:
        execution = ClaimedRun(
            run_id=context["run_id"],
            context=context,
            history=[],
            task="Synthetic",
            kind="benchmark",
            task_metadata={"task_id": "T6", "split": "development", "repetition": 1},
            executor="simulation",
            run_token=client.headers["X-Run-Token"],
            lease_seconds=60,
            heartbeat_seconds=15,
        )

        async def run():
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(respond),
                base_url="http://test",
                headers=client.worker_headers,
            ) as http:
                tools = AsyncToolClient(http, execution)
                with pytest.raises(ToolCallError) as error:
                    await tools.call("salvar_minuta", arguments)
                return tools.calls, error.value

        records, error = asyncio.run(run())
    else:
        tools = ToolClient(
            "http://test",
            client.worker_headers["Authorization"].removeprefix("Bearer "),
            context,
            client.headers["X-Run-Token"],
        )
        tools.client.close()
        tools.client = httpx.Client(
            transport=httpx.MockTransport(respond),
            base_url="http://test",
            headers={**client.worker_headers, "X-Run-Token": client.headers["X-Run-Token"]},
        )
        try:
            with pytest.raises(ToolCallError) as captured:
                tools.call("salvar_minuta", arguments)
            records, error = tools.calls, captured.value
        finally:
            tools.close()
    assert len(seen) == 1 and len(records) == 1 and records[0].status == "error"
    assert error.error is None and not transient(error) and "SYNTHETIC-PRIVATE" not in str(error)
    assert artifact_count(engine, context) == 1


def test_draft_client_validates_all_context_fields_uuid_timezone_and_hash(client, context, corpus):
    body = write_body(context, corpus)
    good = write(client, body).json()
    variants = [
        {**good, "artifact_id": "invalid"},
        {**good, "persisted_at": "2026-10-29T10:00:00"},
        {**good, "content_sha256": "0" * 64},
    ]
    for field in ("run_id", "process_id", "corpus_version", "requirements_version"):
        variants.append(
            {**good, field: str(uuid4()) if field == "run_id" else "SYNTHETIC-PRIVATE-OTHER"}
        )
    for value in variants:
        response = httpx.Response(
            200, json=value, request=httpx.Request("POST", "http://test/tools/salvar_minuta")
        )
        with pytest.raises(ToolCallError) as error:
            tool_outcome(response, "salvar_minuta", context, body)
        assert not transient(error.value) and "SYNTHETIC-PRIVATE" not in str(error.value)
    assert (
        tool_outcome(
            httpx.Response(
                200, json=good, request=httpx.Request("POST", "http://test/tools/salvar_minuta")
            ),
            "salvar_minuta",
            context,
            body,
        )
        == good
    )

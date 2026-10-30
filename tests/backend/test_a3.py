"""A3: operator queue quota, idempotency, isolation and transactional races."""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import ToolError
from services.backend.app import create_app
from services.backend.auth import authenticate, provision
from services.backend.execution import ExecutionService
from services.backend.schema import events, messages, permissions, runs
from services.backend.storage import make_engine


@pytest.fixture(autouse=True)
def default_queue_configuration(monkeypatch):
    monkeypatch.delenv("RUN_MAX_QUEUED_PER_OPERATOR", raising=False)
    monkeypatch.setenv("ENABLED_EXECUTORS", "simulation")


def body(corpus, key=None):
    return {
        **{
            k: getattr(corpus[0], k)
            for k in ("process_id", "corpus_version", "requirements_version")
        },
        "task": "Synthetic A3 task",
        "task_id": "DEV-001",
        "idempotency_key": key or str(uuid4()),
    }


def send(client, value, headers=None):
    return client.post("/runs", json=value, headers=headers or client.operator_headers)


def owner(client, engine):
    return authenticate(engine, client.operator_headers["Authorization"])["principal_id"]


def counts(engine, principal_id):
    with engine.connect() as conn:
        owned = select(runs.c.run_id).where(runs.c.owner_id == principal_id)
        return (
            conn.execute(
                select(func.count()).select_from(runs).where(runs.c.owner_id == principal_id)
            ).scalar_one(),
            conn.execute(
                select(func.count())
                .select_from(runs)
                .where(runs.c.owner_id == principal_id, runs.c.status == "queued")
            ).scalar_one(),
            conn.execute(
                select(func.count()).select_from(events).where(events.c.run_id.in_(owned))
            ).scalar_one(),
            conn.execute(
                select(func.count()).select_from(messages).where(messages.c.run_id.in_(owned))
            ).scalar_one(),
        )


def assert_limit(response):
    assert response.status_code == 429, response.text
    error = ToolError.model_validate(response.json())
    assert error.code == "resource_limit" and error.retryable is True
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A3" not in response.text


def fill(client, corpus, amount):
    values = [body(corpus) for _ in range(amount)]
    responses = [send(client, value) for value in values]
    assert all(response.status_code == 202 for response in responses)
    return values, responses


def test_twentieth_is_allowed_replay_precedes_quota_and_claim_frees_slot(client, corpus, engine):
    values, responses = fill(client, corpus, 20)
    principal_id = owner(client, engine)
    assert counts(engine, principal_id) == (20, 20, 20, 0)
    refused = body(corpus, "retry-after-capacity")
    assert_limit(send(client, refused))
    assert counts(engine, principal_id) == (20, 20, 20, 0)
    replay = send(client, values[0])
    assert replay.status_code == 202 and replay.json()["run_id"] == responses[0].json()["run_id"]
    changed = send(client, {**values[0], "task": "PRIVATE-A3 different input"})
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    claimed = client.post(
        "/runs/claim", json={"executor": "simulation", "run_id": responses[0].json()["run_id"]}
    )
    assert claimed.status_code == 200
    assert send(client, refused).status_code == 202
    assert counts(engine, principal_id) == (21, 20, 22, 0)


def test_last_slot_is_serialized_across_independent_apps(client, corpus, engine):
    fill(client, corpus, 19)
    principal_id = owner(client, engine)
    second_engine = make_engine(engine.url)
    with TestClient(create_app(second_engine)) as second:
        contenders = [body(corpus), body(corpus)]
        barrier = Barrier(2)

        def compete(index):
            barrier.wait(timeout=10)
            api = client if index == 0 else second
            return send(api, contenders[index], client.operator_headers)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(compete, range(2)))
        assert sorted(r.status_code for r in responses) == [202, 429]
        assert counts(engine, principal_id) == (20, 20, 20, 0)
        winner = next(i for i, response in enumerate(responses) if response.status_code == 202)
        with ThreadPoolExecutor(max_workers=2) as pool:
            replays = list(
                pool.map(
                    lambda api: send(api, contenders[winner], client.operator_headers),
                    [client, second],
                )
            )
        assert all(response.status_code == 202 for response in replays)
        assert len({response.json()["run_id"] for response in replays}) == 1
        assert counts(engine, principal_id) == (20, 20, 20, 0)


def test_quota_is_per_owner_counts_chat_and_excludes_other_states(client, corpus, engine):
    service = client.app.state.execution
    service.max_queued_per_operator = 2
    principal_id = owner(client, engine)
    # Persisted state fixtures isolate the queue-count rule, not transition semantics.
    for state in ("running", "succeeded", "failed", "timed_out"):
        response = send(client, body(corpus))
        assert response.status_code == 202
        with engine.begin() as conn:
            conn.execute(
                update(runs)
                .where(runs.c.run_id == response.json()["run_id"])
                .values(status=state, started_at=time.time(), lease_until=time.time() + 3600)
            )
    scope = {
        k: getattr(corpus[0], k) for k in ("process_id", "corpus_version", "requirements_version")
    }
    conversation = client.post("/conversations", headers=client.operator_headers, json=scope)
    assert conversation.status_code == 201
    chat = client.post(
        f"/conversations/{conversation.json()['conversation_id']}/messages",
        headers=client.operator_headers,
        json={"content": "Synthetic chat", "idempotency_key": str(uuid4())},
    )
    assert chat.status_code == 202
    assert send(client, body(corpus)).status_code == 202
    assert_limit(send(client, body(corpus)))
    assert counts(engine, principal_id)[1] == 2
    token = uuid4().hex
    provision(
        engine,
        "a3-other-" + uuid4().hex,
        token,
        "operator",
        [(scope["process_id"], scope["corpus_version"])],
    )
    independent = send(client, body(corpus), {"Authorization": "Bearer " + token})
    assert independent.status_code == 202
    assert counts(engine, principal_id)[1] == 2


def test_invalid_scope_and_revoked_grant_keep_precedence_over_quota(client, corpus, engine):
    client.app.state.execution.max_queued_per_operator = 1
    value = body(corpus)
    assert send(client, value).status_code == 202
    assert send(client, body(corpus), {"Authorization": ""}).status_code == 401
    assert send(client, body(corpus), client.worker_headers).status_code == 403
    unknown = send(client, {**body(corpus), "process_id": "PRIVATE-A3-outside-grant"})
    assert unknown.status_code == 403
    mismatch = send(client, {**body(corpus), "requirements_version": "PRIVATE-A3-other"})
    assert mismatch.status_code == 409 and mismatch.json()["code"] == "version_mismatch"
    disabled = send(client, {**body(corpus), "executor": "hermes"})
    assert disabled.status_code == 503 and disabled.json()["code"] == "executor_unavailable"
    principal_id = owner(client, engine)
    with engine.begin() as conn:
        conn.execute(delete(permissions).where(permissions.c.principal_id == principal_id))
    assert send(client, value).status_code == 403
    assert counts(engine, principal_id) == (1, 1, 1, 0)


def test_run_and_event_rollback_release_capacity_and_keep_key_reusable(client, corpus, engine):
    client.app.state.execution.max_queued_per_operator = 1
    value = body(corpus)

    def unavailable(conn, cursor, statement, parameters, execution_context, many):
        if statement.startswith("INSERT INTO run_events"):
            raise SQLAlchemyError("PRIVATE-A3 event failed")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = send(client, value)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503 and "PRIVATE-A3" not in response.text
    assert counts(engine, owner(client, engine)) == (0, 0, 0, 0)
    assert send(client, value).status_code == 202
    assert_limit(send(client, body(corpus)))
    assert counts(engine, owner(client, engine)) == (1, 1, 1, 0)


def test_queue_configuration_is_positive_and_default_is_twenty(engine, monkeypatch):
    assert ExecutionService(engine).max_queued_per_operator == 20
    monkeypatch.setenv("RUN_MAX_QUEUED_PER_OPERATOR", "3")
    assert ExecutionService(engine).max_queued_per_operator == 3
    for invalid in ("0", "-1", "not-a-number"):
        monkeypatch.setenv("RUN_MAX_QUEUED_PER_OPERATOR", invalid)
        with pytest.raises(ValueError):
            ExecutionService(engine)


def test_one_owner_cannot_multiply_quota_by_using_another_granted_process(client, corpus, engine):
    from pipelines.documents.ingest import chunk_document
    from services.backend.storage import ingest

    process, document = corpus
    other_process = process.model_copy(update={"process_id": "PROC-A3-" + uuid4().hex[:10]})
    other_document = document.model_copy(update={"process_id": other_process.process_id})
    ingest(engine, other_process, other_document, chunk_document(other_document))
    principal_id = owner(client, engine)
    provision(
        engine,
        principal_id,
        client.operator_headers["Authorization"].split()[1],
        "operator",
        [
            (process.process_id, process.corpus_version),
            (other_process.process_id, other_process.corpus_version),
        ],
        can_write=True,
    )
    client.app.state.execution.max_queued_per_operator = 1
    assert send(client, body(corpus)).status_code == 202
    second_scope = {**body(corpus), "process_id": other_process.process_id}
    assert_limit(send(client, second_scope))
    assert counts(engine, principal_id) == (1, 1, 1, 0)

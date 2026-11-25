"""A5: passive queue expiry, boundary races and preserved persisted evidence."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import RunResponse
from services.backend import execution
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.execution import ExecutionService
from services.backend.schema import events, runs
from services.backend.storage import make_engine
from tests.backend.test_a3 import body, counts, owner, send
from tests.backend.test_a4 import create, message, post
from tests.backend.test_tool_calls import write_body


@pytest.fixture(autouse=True)
def queue_settings(monkeypatch):
    monkeypatch.delenv("RUN_QUEUE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("RUN_MAX_QUEUED_PER_OPERATOR", raising=False)
    monkeypatch.setenv("ENABLED_EXECUTORS", "simulation")


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=10000.0)
    original = execution.time
    monkeypatch.setattr(
        execution,
        "time",
        SimpleNamespace(
            time=lambda: state.now,
            perf_counter=original.perf_counter,
        ),
    )
    return state


def row(engine, run_id):
    with engine.connect() as conn:
        return dict(conn.execute(select(runs).where(runs.c.run_id == run_id)).mappings().one())


def terminal_events(engine, run_id):
    with engine.connect() as conn:
        return [
            dict(item)
            for item in conn.execute(
                select(events).where(events.c.run_id == run_id, events.c.kind == "done")
            ).mappings()
        ]


def snapshot(client, run_id):
    return client.get(f"/runs/{run_id}", headers=client.operator_headers)


def assert_timeout(response):
    assert response.status_code == 200, response.text
    result = RunResponse.model_validate(response.json())
    assert result.status == "timed_out" and result.result.error_code == "queue_timeout"
    assert result.started_at is None
    assert response.headers["cache-control"] == "no-store"


def test_get_expires_at_exact_queue_boundary_once_and_keeps_access_rules(
    client, corpus, engine, clock
):
    created = send(client, body(corpus))
    assert created.status_code == 202
    rid = created.json()["run_id"]
    before = row(engine, rid)
    clock.now += 299.999
    assert snapshot(client, rid).json()["status"] == "queued"
    clock.now = before["created_at"] + 300.0
    timed = snapshot(client, rid)
    assert_timeout(timed)
    assert timed.json()["finished_at"] == clock.now
    assert snapshot(client, rid).json() == timed.json()
    assert len(terminal_events(engine, rid)) == 1
    assert terminal_events(engine, rid)[0]["payload"] == {
        "status": "timed_out",
        "error_code": "queue_timeout",
    }
    assert row(engine, rid)["history"] == before["history"]
    assert row(engine, rid)["created_at"] == before["created_at"]
    assert client.get(f"/runs/{rid}").status_code == 403
    assert client.get(f"/runs/{rid}", headers={"Authorization": ""}).status_code == 401
    token = uuid4().hex
    provision(
        engine,
        "a5-other-" + uuid4().hex,
        token,
        "operator",
        [(corpus[0].process_id, corpus[0].corpus_version)],
    )
    assert (
        client.get(f"/runs/{rid}", headers={"Authorization": "Bearer " + token}).status_code == 404
    )
    assert snapshot(client, str(uuid4())).status_code == 404
    assert snapshot(client, "PRIVATE-A5-invalid").status_code == 422
    # The server-only cause is accepted in StoredResult, not in worker AgentResult.
    forged = client.post(
        f"/runs/{rid}/result", json={"status": "timed_out", "error_code": "queue_timeout"}
    )
    assert forged.status_code == 422 and forged.json()["code"] == "validation_error"
    stream = client.get(f"/runs/{rid}/events", headers=client.operator_headers)
    assert stream.status_code == 200 and '"error_code": "queue_timeout"' in stream.text


@pytest.mark.parametrize("producer", ["benchmark", "chat"])
def test_creation_expires_queue_without_get_and_replay_does_not_resurrect(
    client, corpus, engine, clock, producer
):
    client.app.state.execution.max_queued_per_operator = 1
    if producer == "chat":
        cid = create(client, corpus)["conversation_id"]
        original, new = message(), message()

        def enqueue(value):
            return post(client, cid, value)
    else:
        original, new = body(corpus), body(corpus)

        def enqueue(value):
            return send(client, value)

    first = enqueue(original)
    assert first.status_code == 202
    old_id = first.json()["run_id"]
    clock.now += 300.0
    second = enqueue(new)
    assert second.status_code == 202
    old = row(engine, old_id)
    assert old["status"] == "timed_out" and old["result"]["error_code"] == "queue_timeout"
    assert counts(engine, owner(client, engine)) == (2, 1, 3, 2 if producer == "chat" else 0)
    replay = enqueue(original)
    assert replay.status_code == 202 and replay.json()["run_id"] == old_id
    assert replay.json()["status"] == "timed_out"
    assert len(terminal_events(engine, old_id)) == 1
    claimed = client.post("/runs/claim", json={"executor": "simulation"})
    assert claimed.status_code == 200 and claimed.json()["run_id"] == second.json()["run_id"]
    if producer == "chat":
        assert claimed.json()["history"] == [{"role": "user", "content": new["content"]}]


def test_claim_retires_old_queue_and_only_delivers_fresh_candidate(client, corpus, engine, clock):
    old = send(client, body(corpus)).json()["run_id"]
    clock.now += 299.0
    fresh = send(client, body(corpus)).json()["run_id"]
    clock.now += 1.0
    missed = client.post("/runs/claim", json={"executor": "simulation", "run_id": old})
    assert missed.status_code == 204 and not missed.content
    assert row(engine, old)["result"]["error_code"] == "queue_timeout"
    claimed = client.post("/runs/claim", json={"executor": "simulation"})
    assert claimed.status_code == 200 and claimed.json()["run_id"] == fresh
    assert row(engine, old)["worker_id"] is None
    assert len(terminal_events(engine, old)) == 1


def test_claim_rechecks_deadline_after_initial_expiry_pass(
    client, corpus, engine, clock, monkeypatch
):
    rid = send(client, body(corpus)).json()["run_id"]
    deadline = clock.now + 300.0
    clock.now = deadline - 0.001
    original = client.app.state.execution.expire

    def cross_deadline():
        original()
        clock.now = deadline

    monkeypatch.setattr(client.app.state.execution, "expire", cross_deadline)
    claimed = client.post("/runs/claim", json={"executor": "simulation", "run_id": rid})
    assert claimed.status_code == 204
    assert row(engine, rid)["status"] == "timed_out"
    assert row(engine, rid)["worker_id"] is None
    assert len(terminal_events(engine, rid)) == 1


def test_creation_rechecks_expiry_before_queue_quota(client, corpus, engine, clock, monkeypatch):
    service = client.app.state.execution
    service.max_queued_per_operator = 1
    rid = send(client, body(corpus)).json()["run_id"]
    deadline = clock.now + 300.0
    clock.now = deadline - 0.001
    original = service.expire

    def cross_deadline():
        original()
        clock.now = deadline

    monkeypatch.setattr(service, "expire", cross_deadline)
    assert send(client, body(corpus)).status_code == 202
    assert row(engine, rid)["result"]["error_code"] == "queue_timeout"
    assert counts(engine, owner(client, engine)) == (2, 1, 3, 0)


def test_running_keeps_worker_timeout_partial_history_and_confirmed_artifact(
    client, corpus, engine, clock, context
):
    rid = context["run_id"]
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.run_id == rid).values(created_at=clock.now - 301.0))
    assert snapshot(client, rid).json()["status"] == "running"
    saved = client.post("/tools/salvar_minuta", json=write_body(context, corpus))
    assert saved.status_code == 200
    assert (
        client.post(
            f"/runs/{rid}/events",
            json={"event_id": str(uuid4()), "kind": "text_delta", "text": "Synthetic A5 partial"},
        ).status_code
        == 200
    )
    history = row(engine, rid)["history"]
    clock.now += 61.0
    response = snapshot(client, rid)
    assert response.status_code == 200 and response.json()["status"] == "timed_out"
    assert response.json()["result"]["error_code"] == "worker_timeout"
    assert response.json()["partial_answer"] == "Synthetic A5 partial"
    assert response.json()["artifacts"][0]["artifact_id"] == saved.json()["artifact_id"]
    assert row(engine, rid)["history"] == history
    fetched = client.get(
        f"/artifacts/{saved.json()['artifact_id']}", headers=client.operator_headers
    )
    assert fetched.status_code == 200 and fetched.json()["receipt"] == saved.json()
    assert len(terminal_events(engine, rid)) == 1


def test_timeout_state_and_done_event_roll_back_together(client, corpus, engine, clock):
    rid = send(client, body(corpus)).json()["run_id"]
    clock.now += 300.0

    def unavailable(conn, cursor, statement, parameters, execution_context, many):
        if statement.startswith("INSERT INTO run_events"):
            raise SQLAlchemyError("PRIVATE-A5 terminal insert")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        failed = snapshot(client, rid)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert failed.status_code == 503 and "PRIVATE-A5" not in failed.text
    assert row(engine, rid)["status"] == "queued" and row(engine, rid)["result"] is None
    assert row(engine, rid)["finished_at"] is None and terminal_events(engine, rid) == []
    assert_timeout(snapshot(client, rid))
    assert len(terminal_events(engine, rid)) == 1


def test_expiry_and_claim_across_apps_produce_one_terminal_event(client, corpus, engine, clock):
    rid = send(client, body(corpus)).json()["run_id"]
    clock.now += 300.0
    with TestClient(create_app(make_engine(engine.url))) as second:
        barrier = Barrier(2)

        def operate(index):
            barrier.wait(timeout=10)
            if index == 0:
                return snapshot(client, rid)
            return second.post(
                "/runs/claim",
                headers=client.worker_headers,
                json={"executor": "simulation", "run_id": rid},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(operate, range(2)))
    assert_timeout(responses[0])
    assert responses[1].status_code == 204
    assert len(terminal_events(engine, rid)) == 1
    assert row(engine, rid)["worker_id"] is None


def test_queue_timeout_configuration_is_positive_and_independent(engine, monkeypatch):
    monkeypatch.setenv("RUN_TIMEOUT_SECONDS", "123")
    assert ExecutionService(engine).queue_timeout_seconds == 300
    monkeypatch.setenv("RUN_QUEUE_TIMEOUT_SECONDS", "7")
    service = ExecutionService(engine)
    assert service.queue_timeout_seconds == 7 and service.max_run_seconds == 123
    for invalid in ("0", "-1", "not-a-number"):
        monkeypatch.setenv("RUN_QUEUE_TIMEOUT_SECONDS", invalid)
        with pytest.raises(ValueError):
            ExecutionService(engine)

"""A8: bounded durable events, one reserved terminal slot, no duplicated effects."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import AgentEvent
from services.backend import execution
from services.backend.auth import authenticate
from services.backend.schema import artifacts, events, runs
from tests.backend import test_a5
from tests.backend.test_a5 import row, snapshot, terminal_events
from tests.backend.test_a7 import start
from tests.backend.test_execution import finish
from tests.backend.test_tool_calls import history, write_body


@pytest.fixture
def clock(monkeypatch):
    return test_a5.clock.__wrapped__(monkeypatch)


def seed(engine, rid, upto, now):
    with engine.begin() as conn:
        current = conn.execute(
            select(runs.c.event_sequence).where(runs.c.run_id == rid)
        ).scalar_one()
        conn.execute(
            insert(events),
            [
                dict(
                    run_id=rid,
                    sequence=i,
                    event_id=str(uuid4()),
                    kind="status",
                    payload={"text": "Synthetic bounded event"},
                    created_at=now,
                )
                for i in range(current + 1, upto + 1)
            ],
        )
        conn.execute(update(runs).where(runs.c.run_id == rid).values(event_sequence=upto))


def publish(client, rid, headers, event_id=None, text="Synthetic partial", kind="text_delta"):
    return client.post(
        f"/runs/{rid}/events",
        headers=headers,
        json={
            "event_id": event_id or str(uuid4()),
            "kind": kind,
            "text": text,
        },
    )


def assert_limit(client, engine, rid, expected):
    result = snapshot(client, rid)
    assert result.status_code == 200
    assert result.json()["status"] == "failed"
    assert result.json()["result"]["error_code"] == "event_limit"
    terminal = terminal_events(engine, rid)
    assert len(terminal) == 1 and terminal[0]["sequence"] == expected
    with engine.connect() as conn:
        sequences = (
            conn.execute(
                select(events.c.sequence).where(events.c.run_id == rid).order_by(events.c.sequence)
            )
            .scalars()
            .all()
        )
    assert sequences == list(range(1, expected + 1))


def test_real_twenty_thousand_boundary_reserves_terminal_and_preserves_replay(
    client, corpus, engine, clock
):
    assert execution.MAX_EVENTS_PER_RUN == 20_000
    run, headers = start(client, corpus)
    rid = run["run_id"]
    seed(engine, rid, 19_998, clock.now)
    identity = str(uuid4())
    accepted = publish(client, rid, headers, identity)
    assert accepted.status_code == 200 and accepted.json()["sequence"] == 19_999
    assert publish(client, rid, headers, identity).json() == accepted.json()
    assert publish(client, rid, headers, identity, text="Changed").status_code == 409
    limited = publish(client, rid, headers)
    assert limited.status_code == 429 and limited.json()["code"] == "resource_limit"
    assert limited.json()["retryable"] is False
    assert limited.headers["cache-control"] == "no-store"
    assert_limit(client, engine, rid, 20_000)
    assert snapshot(client, rid).json()["partial_answer"] == "Synthetic partial"
    assert publish(client, rid, headers).status_code == 409
    assert finish(client, run, headers, "Synthetic partial").status_code == 409
    stream = client.get(f"/runs/{rid}/events?after=19998", headers=client.operator_headers)
    assert stream.status_code == 200 and '"error_code": "event_limit"' in stream.text
    assert stream.text.count("event: done") == 1 and "id: 20000" in stream.text
    assert len(terminal_events(engine, rid)) == 1


def test_tool_event_cannot_bypass_limit_and_rollback_preserves_previous_artifact(
    client, corpus, engine, clock, monkeypatch
):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 4)
    run, headers = start(client, corpus)
    rid = run["run_id"]
    first = client.post(
        "/tools/salvar_minuta",
        headers={**headers, "X-Tool-Call-Id": "first"},
        json=write_body(run["context"], corpus),
    )
    assert first.status_code == 200
    refused = client.post(
        "/tools/salvar_minuta",
        headers={**headers, "X-Tool-Call-Id": "second"},
        json=write_body(run["context"], corpus, key="other"),
    )
    assert refused.status_code == 429
    assert_limit(client, engine, rid, 4)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count()).select_from(artifacts).where(artifacts.c.run_id == rid)
            ).scalar_one()
            == 1
        )
    assert [item["http_status"] for item in history(client, engine, rid)] == [200, 429]
    assert (
        client.get(
            f"/artifacts/{first.json()['artifact_id']}", headers=client.operator_headers
        ).status_code
        == 200
    )


def test_failed_tool_attempt_keeps_ledger_when_terminal_slot_is_needed(
    client, corpus, engine, clock, monkeypatch
):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 3)
    run, headers = start(client, corpus)
    response = client.post(
        "/tools/ler_documento", headers=headers, json={**run["context"], "document_id": "MISSING"}
    )
    assert response.status_code == 404
    assert_limit(client, engine, run["run_id"], 3)
    assert history(client, engine, run["run_id"])[0]["http_status"] == 404


@pytest.mark.parametrize("opponent", ["event", "finish"])
def test_concurrent_limit_has_one_terminal_outcome(
    client, corpus, engine, clock, monkeypatch, opponent
):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 4)
    run, headers = start(client, corpus)
    rid = run["run_id"]
    seed(engine, rid, 3, clock.now)
    barrier = Barrier(2)

    def operate(index):
        barrier.wait(timeout=10)
        if index == 0 or opponent == "event":
            return publish(client, rid, headers)
        return finish(client, run, headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(operate, range(2)))
    assert all(r.status_code in {200, 409, 429} for r in responses)
    assert row(engine, rid)["status"] in {"failed", "succeeded"}
    assert row(engine, rid)["event_sequence"] == 4 and len(terminal_events(engine, rid)) == 1


def test_terminal_persistence_failure_is_retryable_without_partial_state(
    client, corpus, engine, clock, monkeypatch
):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 3)
    run, headers = start(client, corpus)
    rid = run["run_id"]

    def unavailable(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {events.name}"):
            raise SQLAlchemyError("PRIVATE-A8 terminal insert")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = publish(client, rid, headers)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503 and "PRIVATE-A8" not in response.text
    assert row(engine, rid)["status"] == "running" and terminal_events(engine, rid) == []
    assert publish(client, rid, headers).status_code == 429
    assert_limit(client, engine, rid, 3)


def test_reserved_slot_accepts_normal_finish_but_not_forged_server_cause(
    client, corpus, engine, clock, monkeypatch
):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 3)
    run, headers = start(client, corpus)
    rid = run["run_id"]
    forged = client.post(
        f"/runs/{rid}/result",
        headers=headers,
        json={"status": "failed", "error_code": "event_limit"},
    )
    assert forged.status_code == 422
    assert publish(client, rid, headers, kind="done").status_code == 422
    assert finish(client, run, headers).status_code == 200
    assert row(engine, rid)["event_sequence"] == 3 and len(terminal_events(engine, rid)) == 1


def test_limit_recovery_uses_only_one_pool_connection(client, corpus, engine, clock, monkeypatch):
    monkeypatch.setattr(execution, "MAX_EVENTS_PER_RUN", 3)
    run, headers = start(client, corpus)
    actor = authenticate(engine, headers["Authorization"])
    single = create_engine(engine.url, pool_size=1, max_overflow=0, pool_timeout=0.1)
    try:
        service = execution.ExecutionService(single)
        with pytest.raises(execution.EventLimitReached):
            service.add_event(
                actor,
                run["run_id"],
                run["run_token"],
                AgentEvent(
                    event_id=uuid4(),
                    kind="status",
                    text="Synthetic pool boundary",
                ),
            )
        assert_limit(client, engine, run["run_id"], 3)
    finally:
        single.dispose()

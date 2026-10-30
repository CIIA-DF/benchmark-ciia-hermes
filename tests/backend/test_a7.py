"""A7: heartbeat presence and lease have one authorized transactional outcome."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, update
from sqlalchemy.exc import SQLAlchemyError

from services.backend.app import create_app
from services.backend.auth import authenticate
from services.backend.schema import principals
from services.backend.storage import make_engine
from tests.backend import test_a5
from tests.backend.test_a5 import row, snapshot, terminal_events
from tests.backend.test_a6 import presence
from tests.backend.test_execution import claim, conversation, finish, send


@pytest.fixture
def clock(monkeypatch):
    return test_a5.clock.__wrapped__(monkeypatch)


def start(client, corpus):
    send(client, conversation(client, corpus))
    return claim(client)


def test_heartbeat_refreshes_lease_and_presence_together(client, corpus, engine, clock):
    run, headers = start(client, corpus)
    before = row(engine, run["run_id"])
    clock.now += 5
    response = client.post(f"/runs/{run['run_id']}/heartbeat", headers=headers)
    assert response.status_code == 200 and response.json() == {"status": "running"}
    assert response.headers["cache-control"] == "no-store"
    after = row(engine, run["run_id"])
    assert after["lease_until"] == before["lease_until"] + 5
    observed = presence(client, engine)
    assert observed["source"] == "heartbeat" and observed["observed_at"] == clock.now
    assert after["event_sequence"] == before["event_sequence"]


@pytest.mark.parametrize("change", ["executor", "role", "token_sha256"])
def test_stale_identity_cannot_refresh_lease_or_presence(
    client, corpus, engine, clock, monkeypatch, change
):
    run, headers = start(client, corpus)
    actor = authenticate(engine, headers["Authorization"])
    before = row(engine, run["run_id"])
    old_presence = dict(presence(client, engine))
    clock.now += 5
    with engine.begin() as conn:
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == actor["principal_id"])
            .values(
                **{
                    change: {"executor": "hermes", "role": "operator", "token_sha256": "revoked"}[
                        change
                    ]
                }
            )
        )
    monkeypatch.setattr("services.backend.app.authenticate", lambda *_: actor)
    response = client.post(f"/runs/{run['run_id']}/heartbeat", headers=headers)
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
    assert row(engine, run["run_id"])["lease_until"] == before["lease_until"]
    # Read with the original worker ID: the credential itself may have been revoked.
    from sqlalchemy import select

    from services.backend.schema import worker_presence

    with engine.connect() as conn:
        assert dict(conn.execute(select(worker_presence)).mappings().one()) == old_presence


def test_invalid_lease_does_not_refresh_presence(client, corpus, engine, clock):
    run, headers = start(client, corpus)
    previous = dict(presence(client, engine))
    before = row(engine, run["run_id"])
    clock.now += 1
    for token in ("", "wrong"):
        response = client.post(
            f"/runs/{run['run_id']}/heartbeat", headers={**headers, "X-Run-Token": token}
        )
        assert response.status_code == 403
    assert dict(presence(client, engine)) == previous
    assert row(engine, run["run_id"])["lease_until"] == before["lease_until"]


def test_sql_failure_rolls_back_presence_and_lease(client, corpus, engine, clock):
    run, headers = start(client, corpus)
    previous = dict(presence(client, engine))
    before = row(engine, run["run_id"])
    clock.now += 2

    def unavailable(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE runs SET lease_until"):
            raise SQLAlchemyError("PRIVATE-A7 lease update")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.post(f"/runs/{run['run_id']}/heartbeat", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503 and "PRIVATE-A7" not in response.text
    assert dict(presence(client, engine)) == previous
    assert row(engine, run["run_id"])["lease_until"] == before["lease_until"]


@pytest.mark.parametrize("opponent", ["expiry", "finish"])
def test_heartbeat_races_do_not_resurrect_terminal_run(client, corpus, engine, clock, opponent):
    run, headers = start(client, corpus)
    rid = run["run_id"]
    old_presence = dict(presence(client, engine))
    if opponent == "expiry":
        clock.now = row(engine, rid)["lease_until"]
    else:
        clock.now += 1
    with TestClient(create_app(make_engine(engine.url))) as second:
        barrier = Barrier(2)

        def operate(index):
            barrier.wait(timeout=10)
            if index == 0:
                return client.post(f"/runs/{rid}/heartbeat", headers=headers)
            if opponent == "expiry":
                return second.get(f"/runs/{rid}", headers=client.operator_headers)
            return finish(second, run, headers)

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(operate, range(2)))
    assert responses[1].status_code == 200, responses[1].text
    assert responses[0].status_code in ({409} if opponent == "expiry" else {200, 409})
    assert snapshot(client, rid).json()["status"] == (
        "timed_out" if opponent == "expiry" else "succeeded"
    )
    assert len(terminal_events(engine, rid)) == 1
    before = row(engine, rid)["lease_until"]
    observed = dict(presence(client, engine))
    assert client.post(f"/runs/{rid}/heartbeat", headers=headers).status_code == 409
    assert row(engine, rid)["lease_until"] == before
    assert dict(presence(client, engine)) == observed
    if opponent == "expiry":
        assert observed == old_presence

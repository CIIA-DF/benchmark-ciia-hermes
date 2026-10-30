"""A6: successful polling is observed, including an empty queue."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import inspect, select, update

from services.backend.auth import authenticate
from services.backend.migrate import migrate
from services.backend.schema import principals, runs, worker_presence
from tests.backend.test_a3 import body, send


def presence(client, engine):
    actor = authenticate(engine, client.worker_headers["Authorization"])
    with engine.connect() as conn:
        return (
            conn.execute(
                select(worker_presence).where(
                    worker_presence.c.principal_id == actor["principal_id"]
                )
            )
            .mappings()
            .first()
        )


def test_empty_poll_updates_one_durable_presence_without_exposing_secret(client, engine):
    for _ in range(2):
        response = client.post("/runs/claim", json={"executor": "simulation"})
        assert response.status_code == 204 and response.content == b""
        assert response.headers["cache-control"] == "no-store"
    observed = presence(client, engine)
    assert observed["executor"] == "simulation" and observed["source"] == "claim"
    assert observed["observed_at"] > 0
    assert set(observed) == {"principal_id", "executor", "observed_at", "source"}


def test_invalid_poll_and_stale_authenticated_role_do_not_record_presence(
    client, engine, monkeypatch
):
    assert (
        client.post(
            "/runs/claim", headers={"Authorization": ""}, json={"executor": "simulation"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/runs/claim", headers=client.operator_headers, json={"executor": "simulation"}
        ).status_code
        == 403
    )
    assert client.post("/runs/claim", json={"executor": "hermes"}).status_code == 403
    actor = authenticate(engine, client.worker_headers["Authorization"])
    with engine.begin() as conn:
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == actor["principal_id"])
            .values(role="operator")
        )
    monkeypatch.setattr("services.backend.app.authenticate", lambda *_: actor)
    assert client.post("/runs/claim", json={"executor": "simulation"}).status_code == 403
    with engine.connect() as conn:
        assert conn.execute(select(worker_presence)).first() is None


def test_claim_is_exclusive_and_scoped_while_recording_presence(client, corpus, engine):
    queued = send(client, body(corpus)).json()["run_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    "/runs/claim", json={"executor": "simulation", "run_id": queued}
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in responses) == [200, 204]
    assert presence(client, engine)["source"] == "claim"
    unknown = client.post("/runs/claim", json={"executor": "simulation", "run_id": str(uuid4())})
    assert unknown.status_code == 204
    with engine.connect() as conn:
        assert (
            conn.execute(select(runs.c.status).where(runs.c.run_id == queued)).scalar_one()
            == "running"
        )


def test_presence_migration_preserves_runs_without_backfill(client, corpus, engine):
    rid = send(client, body(corpus)).json()["run_id"]
    migrate(engine, "0006", downgrade=True)
    assert "worker_presence" not in inspect(engine).get_table_names()
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(select(worker_presence)).first() is None
        assert conn.execute(select(runs.c.run_id).where(runs.c.run_id == rid)).scalar_one() == rid
    assert (
        client.post("/runs/claim", json={"executor": "simulation", "run_id": rid}).status_code
        == 200
    )

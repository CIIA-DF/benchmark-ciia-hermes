"""P9a: limite de 100.000 caracteres por contador, sem reler os deltas a cada evento."""

from uuid import uuid4

from sqlalchemy import select

from services.backend.migrate import migrate
from services.backend.schema import runs
from tests.backend.test_compat import queue_and_claim


def post_delta(client, execution, text, event_id=None):
    headers = {**client.worker_headers, "X-Run-Token": execution.run_token}
    return client.post(
        f"/runs/{execution.run_id}/events",
        headers=headers,
        json={"event_id": event_id or str(uuid4()), "kind": "text_delta", "text": text},
    )


def partial_chars(engine, run_id):
    with engine.connect() as conn:
        return conn.execute(
            select(runs.c.partial_chars).where(runs.c.run_id == str(run_id))
        ).scalar_one()


def test_limit_is_exact_and_replay_does_not_count_twice(client, corpus, engine):
    execution = queue_and_claim(client, corpus, "chat")
    first = str(uuid4())
    assert post_delta(client, execution, "a" * 4000, first).status_code == 200
    # Replay idempotente do mesmo evento não soma de novo.
    assert post_delta(client, execution, "a" * 4000, first).status_code == 200
    for _ in range(24):
        assert post_delta(client, execution, "b" * 4000).status_code == 200
    assert partial_chars(engine, execution.run_id) == 100_000
    over = post_delta(client, execution, "c")
    assert over.status_code == 422 and over.json()["code"] == "context_limit"
    assert partial_chars(engine, execution.run_id) == 100_000
    status = client.post(
        f"/runs/{execution.run_id}/events",
        headers={**client.worker_headers, "X-Run-Token": execution.run_token},
        json={"event_id": str(uuid4()), "kind": "status", "text": "status não conta"},
    )
    assert status.status_code == 200
    assert partial_chars(engine, execution.run_id) == 100_000
    stored = client.get(f"/runs/{execution.run_id}", headers=client.operator_headers).json()
    assert len(stored["partial_answer"]) == 100_000


def test_migration_backfills_from_existing_deltas(client, corpus, engine):
    execution = queue_and_claim(client, corpus, "chat")
    for text in ("olá ", "mundo", " ✓"):
        assert post_delta(client, execution, text).status_code == 200
    expected = len("olá mundo ✓")
    assert partial_chars(engine, execution.run_id) == expected
    migrate(engine, "0011", downgrade=True)
    migrate(engine)
    assert partial_chars(engine, execution.run_id) == expected
    assert post_delta(client, execution, "!").status_code == 200
    assert partial_chars(engine, execution.run_id) == expected + 1

"""A4: conversation APIs and the shared chat/benchmark queue transaction."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import ConversationDetail, ConversationResponse
from contracts.models import ToolError
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.schema import conversations, messages, permissions
from services.backend.storage import make_engine
from tests.backend.test_a3 import body, counts, fill, owner


@pytest.fixture(autouse=True)
def conversation_test_configuration(monkeypatch):
    monkeypatch.delenv("RUN_MAX_QUEUED_PER_OPERATOR", raising=False)
    monkeypatch.setenv("ENABLED_EXECUTORS", "simulation")


def scope(corpus):
    return {
        key: getattr(corpus[0], key)
        for key in ("process_id", "corpus_version", "requirements_version")
    }


def create(client, corpus, participant_id=None, headers=None):
    response = client.post(
        "/conversations",
        headers=headers or client.operator_headers,
        json={**scope(corpus), "participant_id": participant_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def post(client, conversation_id, value, headers=None):
    return client.post(
        f"/conversations/{conversation_id}/messages",
        json=value,
        headers=headers or client.operator_headers,
    )


def message(key=None):
    return {"content": "PRIVATE-A4 synthetic question", "idempotency_key": key or str(uuid4())}


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert ToolError.model_validate(response.json()).code == code
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A4" not in response.text


def test_message_quota_replay_and_active_conversation_preserve_atomicity(client, corpus, engine):
    first = create(client, corpus)["conversation_id"]
    second = create(client, corpus)["conversation_id"]
    fill(client, corpus, 19)
    original = message()
    queued = post(client, first, original)
    assert queued.status_code == 202
    principal_id = owner(client, engine)
    assert counts(engine, principal_id) == (20, 20, 20, 1)
    refused = message()
    assert_error(post(client, second, refused), 429, "resource_limit")
    assert counts(engine, principal_id) == (20, 20, 20, 1)
    replay = post(client, first, original)
    assert replay.status_code == 202 and replay.json()["run_id"] == queued.json()["run_id"]
    assert_error(
        post(client, first, {**original, "content": "PRIVATE-A4 changed"}),
        409,
        "idempotency_conflict",
    )
    assert_error(post(client, second, original), 409, "idempotency_conflict")
    assert_error(post(client, first, message()), 409, "conflict")
    claimed = client.post(
        "/runs/claim", json={"executor": "simulation", "run_id": queued.json()["run_id"]}
    )
    assert claimed.status_code == 200
    assert_error(post(client, first, message()), 409, "conflict")
    assert post(client, second, refused).status_code == 202
    assert counts(engine, principal_id) == (21, 20, 22, 2)


@pytest.mark.parametrize(
    "scenario", ["two-conversations", "one-conversation", "benchmark-and-chat"]
)
def test_queue_races_use_one_operator_lock_for_both_producers(client, corpus, engine, scenario):
    first = create(client, corpus)["conversation_id"]
    second = first if scenario == "one-conversation" else create(client, corpus)["conversation_id"]
    client.app.state.execution.max_queued_per_operator = 1
    with TestClient(create_app(make_engine(engine.url))) as other:
        other.app.state.execution.max_queued_per_operator = 1
        barrier = Barrier(2)
        values = [message(), message()]
        benchmark = body(corpus)

        def send(index):
            barrier.wait(timeout=10)
            api = client if index == 0 else other
            if index == 0 and scenario == "benchmark-and-chat":
                return api.post("/runs", headers=client.operator_headers, json=benchmark)
            return post(
                api, first if index == 0 else second, values[index], client.operator_headers
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, range(2)))
        assert sorted(r.status_code for r in responses) == [
            202,
            409 if scenario == "one-conversation" else 429,
        ]
        winner = next(response.json() for response in responses if response.status_code == 202)
        expected_messages = 1 if winner["kind"] == "chat" else 0
        assert counts(engine, owner(client, engine)) == (1, 1, 1, expected_messages)


@pytest.mark.parametrize("table", ["messages", "run_events"])
def test_message_run_and_initial_event_roll_back_together(client, corpus, engine, table):
    cid = create(client, corpus)["conversation_id"]
    client.app.state.execution.max_queued_per_operator = 1
    payload = message()

    def unavailable(conn, cursor, statement, parameters, execution_context, many):
        if statement.startswith(f"INSERT INTO {table}"):
            raise SQLAlchemyError("PRIVATE-A4 synthetic rollback")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        failed = post(client, cid, payload)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert_error(failed, 503, "storage_unavailable")
    assert counts(engine, owner(client, engine)) == (0, 0, 0, 0)
    detail = client.get(f"/conversations/{cid}", headers=client.operator_headers)
    assert detail.status_code == 200 and detail.json()["messages"] == detail.json()["runs"] == []
    accepted = post(client, cid, payload)
    assert accepted.status_code == 202
    replay = post(client, cid, payload)
    assert replay.status_code == 202 and replay.json()["run_id"] == accepted.json()["run_id"]
    assert counts(engine, owner(client, engine)) == (1, 1, 1, 1)


def test_create_conversation_keeps_scope_executor_and_closed_input(client, corpus, engine):
    own = create(client, corpus, str(uuid4()))
    assert ConversationResponse.model_validate(own).executor == "simulation"
    for fields, status, code in [
        ({"process_id": "PRIVATE-A4-outside"}, 403, "forbidden"),
        ({"requirements_version": "PRIVATE-A4-other"}, 409, "version_mismatch"),
        ({"executor": "hermes"}, 503, "executor_unavailable"),
        ({"owner_id": "PRIVATE-A4-owner"}, 422, "validation_error"),
    ]:
        response = client.post(
            "/conversations", headers=client.operator_headers, json={**scope(corpus), **fields}
        )
        assert_error(response, status, code)
    assert_error(client.post("/conversations", json=scope(corpus)), 403, "forbidden")
    assert_error(
        client.post("/conversations", headers={"Authorization": ""}, json=scope(corpus)),
        401,
        "unauthorized",
    )
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(conversations).where(conversations.c.owner_id == owner(client, engine))
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1 and rows[0]["conversation_id"] == own["conversation_id"]


def test_list_filters_never_grant_access_and_revocation_hides_rows(client, corpus, engine):
    participant = str(uuid4())
    first = create(client, corpus, participant)
    second = create(client, corpus, str(uuid4()))
    token = uuid4().hex
    provision(
        engine,
        "a4-other-" + uuid4().hex,
        token,
        "operator",
        [(corpus[0].process_id, corpus[0].corpus_version)],
    )
    foreign = create(client, corpus, participant, {"Authorization": "Bearer " + token})
    listed = client.get("/conversations", headers=client.operator_headers)
    assert listed.status_code == 200 and listed.headers["cache-control"] == "no-store"
    assert {
        str(ConversationResponse.model_validate(row).conversation_id) for row in listed.json()
    } == {first["conversation_id"], second["conversation_id"]}
    filtered = client.get(
        "/conversations", headers=client.operator_headers, params={"participant_id": participant}
    )
    assert [row["conversation_id"] for row in filtered.json()] == [first["conversation_id"]]
    assert_error(
        client.get(f"/conversations/{foreign['conversation_id']}", headers=client.operator_headers),
        404,
        "not_found",
    )
    assert_error(post(client, foreign["conversation_id"], message()), 404, "not_found")
    assert_error(
        client.get(
            "/conversations",
            headers=client.operator_headers,
            params={"participant_id": "PRIVATE-A4-invalid"},
        ),
        422,
        "validation_error",
    )
    assert_error(client.get("/conversations"), 403, "forbidden")
    principal_id = owner(client, engine)
    with engine.begin() as conn:
        conn.execute(delete(permissions).where(permissions.c.principal_id == principal_id))
    empty = client.get(
        "/conversations", headers=client.operator_headers, params={"participant_id": participant}
    )
    assert empty.status_code == 200 and empty.json() == []
    assert_error(
        client.get(f"/conversations/{first['conversation_id']}", headers=client.operator_headers),
        403,
        "forbidden",
    )
    assert_error(post(client, first["conversation_id"], message()), 403, "forbidden")


def test_detail_is_typed_and_corrupt_message_returns_safe_500(client, corpus, engine):
    cid = create(client, corpus)["conversation_id"]
    queued = post(client, cid, message())
    assert queued.status_code == 202
    response = client.get(f"/conversations/{cid}", headers=client.operator_headers)
    assert response.status_code == 200
    detail = ConversationDetail.model_validate(response.json())
    assert len(detail.messages) == len(detail.runs) == 1
    assert detail.messages[0].run_id == detail.runs[0].run_id
    assert detail.runs[0].status == "queued"
    assert_error(
        client.get(f"/conversations/{uuid4()}", headers=client.operator_headers), 404, "not_found"
    )
    assert_error(
        client.get("/conversations/PRIVATE-A4-invalid", headers=client.operator_headers),
        422,
        "validation_error",
    )
    with engine.begin() as conn:
        conn.execute(
            update(messages)
            .where(messages.c.conversation_id == cid)
            .values(role="PRIVATE-A4-invalid")
        )
    assert_error(
        client.get(f"/conversations/{cid}", headers=client.operator_headers),
        500,
        "invalid_response",
    )
    with engine.begin() as conn:
        conn.execute(update(messages).where(messages.c.conversation_id == cid).values(role="user"))
    assert (
        client.get(f"/conversations/{cid}", headers=client.operator_headers).json()
        == response.json()
    )

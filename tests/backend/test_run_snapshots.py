"""Snapshots de execução e conversa coerentes sob gravações concorrentes (A01/A02)."""

from uuid import uuid4

import pytest

from contracts.execution import AgentEvent, AgentResult
from services.backend.auth import authenticate
from tests.backend.test_execution import claim, conversation, send


def actors(client, engine):
    return (
        authenticate(engine, client.operator_headers["Authorization"]),
        authenticate(engine, client.worker_headers["Authorization"]),
    )


def test_run_snapshot_never_loses_concurrent_delta(client, corpus, engine, monkeypatch):
    cid = conversation(client, corpus)
    run_id = send(client, cid).json()["run_id"]
    claimed, headers = claim(client)
    published = client.post(
        f"/runs/{run_id}/events",
        headers=headers,
        json={"event_id": str(uuid4()), "kind": "text_delta", "text": "A"},
    )
    assert published.status_code == 200, published.text
    operator, worker = actors(client, engine)
    service = client.app.state.execution
    original = service.partial
    injected = False

    def interleaved(conn, run, *args, **kwargs):
        # Delta confirmado no meio da leitura do snapshot, como um worker concorrente.
        nonlocal injected
        text = original(conn, run, *args, **kwargs)
        if not injected:
            injected = True
            event = AgentEvent(event_id=uuid4(), kind="text_delta", text="LOST")
            service.add_event(worker, run, claimed["run_token"], event)
        return text

    monkeypatch.setattr(service, "partial", interleaved)
    snapshot = client.get(f"/runs/{run_id}", headers=client.operator_headers).json()
    monkeypatch.undo()
    assert injected
    items, _ = service.read_events(operator, run_id, snapshot["last_event_id"])
    later = "".join(item["payload"]["text"] for item in items if item["kind"] == "text_delta")
    assert snapshot["partial_answer"] + later == "ALOST"


@pytest.mark.parametrize("moment", ["before", "after"])
def test_conversation_snapshot_matches_run_status(client, corpus, engine, monkeypatch, moment):
    cid = conversation(client, corpus)
    run_id = send(client, cid).json()["run_id"]
    claimed, _ = claim(client)
    _, worker = actors(client, engine)
    service = client.app.state.execution
    original = service.public_run
    finished = False

    def interleaved(conn, row):
        # Resultado confirmado antes ou depois da leitura do run dentro do mesmo GET.
        nonlocal finished
        if moment == "before" and not finished:
            finished = True
            service.finish(worker, run_id, claimed["run_token"], AgentResult(**answer))
        value = original(conn, row)
        if moment == "after" and not finished:
            finished = True
            service.finish(worker, run_id, claimed["run_token"], AgentResult(**answer))
        return value

    answer = {"status": "succeeded", "answer": "Resposta final fictícia"}
    monkeypatch.setattr(service, "public_run", interleaved)
    detail = client.get(f"/conversations/{cid}", headers=client.operator_headers).json()
    monkeypatch.undo()
    assert finished
    run_ids = {run["run_id"] for run in detail["runs"]}
    assert {message["run_id"] for message in detail["messages"]} <= run_ids
    for run in detail["runs"]:
        answered = any(
            m["run_id"] == run["run_id"] and m["role"] == "assistant" for m in detail["messages"]
        )
        assert answered == (run["status"] == "succeeded"), (moment, run["status"])
    reread = client.get(f"/conversations/{cid}", headers=client.operator_headers).json()
    assert [m["role"] for m in reread["messages"]] == ["user", "assistant"]
    assert reread["runs"][0]["status"] == "succeeded"

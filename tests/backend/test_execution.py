import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.simulation import SimulationAdapter
from agents.worker import execute
from contracts.execution import ClaimedRun
from services.backend.auth import provision
from services.backend.schema import artifacts, runs


def scope(corpus):
    process, _ = corpus
    return {
        k: getattr(process, k) for k in ("process_id", "corpus_version", "requirements_version")
    }


def conversation(client, corpus):
    response = client.post("/conversations", headers=client.operator_headers, json=scope(corpus))
    assert response.status_code == 201, response.text
    return response.json()["conversation_id"]


def send(client, conversation_id, content="Pergunta fictícia", key=None):
    return client.post(
        f"/conversations/{conversation_id}/messages",
        headers=client.operator_headers,
        json={"content": content, "idempotency_key": key or str(uuid4())},
    )


def claim(client):
    response = client.post(
        "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
    )
    assert response.status_code == 200, response.text
    value = response.json()
    headers = {**client.worker_headers, "X-Run-Token": value["run_token"]}
    return value, headers


def finish(client, run, headers, answer="Resposta fictícia"):
    return client.post(
        f"/runs/{run['run_id']}/result",
        headers=headers,
        json={"status": "succeeded", "answer": answer},
    )


def test_authentication_executor_and_context_isolation(client, corpus):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/health"]["get"]["security"] == []
    assert schema["paths"]["/tools/consultar_processo"]["post"]["security"] == [
        {"BearerAuth": [], "RunToken": []}
    ]
    assert client.get("/conversations", headers={"Authorization": ""}).status_code == 401
    assert client.get("/conversations").status_code == 403
    assert client.get("/processos", headers=client.operator_headers).json()[0]["process_id"] == (
        corpus[0].process_id
    )
    unavailable = client.post(
        "/conversations",
        headers=client.operator_headers,
        json={**scope(corpus), "executor": "hermes"},
    )
    assert unavailable.status_code == 503
    denied = client.post(
        "/conversations",
        headers=client.operator_headers,
        json={**scope(corpus), "process_id": "ANOTHER"},
    )
    assert denied.status_code == 403


def test_memory_and_benchmark_have_separate_contexts(client, corpus):
    cid = conversation(client, corpus)
    assert send(client, cid, "Primeira pergunta").status_code == 202
    first, headers = claim(client)
    assert first["history"] == [{"role": "user", "content": "Primeira pergunta"}]
    assert finish(client, first, headers, "Primeira resposta").status_code == 200
    assert send(client, cid, "E a continuação?").status_code == 202
    second, _ = claim(client)
    assert [m["content"] for m in second["history"]] == [
        "Primeira pergunta",
        "Primeira resposta",
        "E a continuação?",
    ]
    response = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            **scope(corpus),
            "task": "Benchmark isolado",
            "task_id": "DEV-001",
            "idempotency_key": str(uuid4()),
        },
    )
    assert response.status_code == 202
    benchmark, _ = claim(client)
    assert benchmark["kind"] == "benchmark"
    assert benchmark["history"] == [{"role": "user", "content": "Benchmark isolado"}]


def test_message_replay_conflict_and_single_active_run(client, corpus):
    cid, key = conversation(client, corpus), str(uuid4())
    first = send(client, cid, key=key)
    replay = send(client, cid, key=key)
    assert replay.status_code == 202
    assert first.json()["run_id"] == replay.json()["run_id"]
    assert send(client, cid, "Texto diferente", key).status_code == 409
    assert send(client, cid).status_code == 409


def test_duplicate_and_concurrent_claim(client, corpus):
    cid = conversation(client, corpus)
    send(client, cid)

    def reserve(_):
        return client.post(
            "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, range(2))) == [200, 204]


def test_targeted_claim_does_not_take_another_queued_run(client, corpus):
    first = send(client, conversation(client, corpus)).json()
    second = send(client, conversation(client, corpus)).json()
    response = client.post(
        "/runs/claim",
        headers=client.worker_headers,
        json={"executor": "simulation", "run_id": second["run_id"]},
    )
    assert response.status_code == 200
    assert response.json()["run_id"] == second["run_id"]
    still_queued = client.get(f"/runs/{first['run_id']}", headers=client.operator_headers)
    assert still_queued.json()["status"] == "queued"


def test_event_replay_sse_cursor_and_result_consistency(client, corpus):
    cid = conversation(client, corpus)
    send(client, cid)
    run, headers = claim(client)
    path = f"/runs/{run['run_id']}"
    event = {"event_id": str(uuid4()), "kind": "text_delta", "text": "Olá, "}
    first = client.post(path + "/events", headers=headers, json=event)
    assert first.status_code == 200
    assert client.post(path + "/events", headers=headers, json=event).json() == first.json()
    assert (
        client.post(
            path + "/events", headers=headers, json={**event, "text": "Diferente"}
        ).status_code
        == 409
    )
    assert finish(client, run, headers, "Resposta divergente").status_code == 422
    client.post(
        path + "/events",
        headers=headers,
        json={"event_id": str(uuid4()), "kind": "text_delta", "text": "mundo!"},
    )
    assert finish(client, run, headers, "Olá, mundo!").status_code == 200
    assert finish(client, run, headers, "Olá, mundo!").status_code == 200
    assert finish(client, run, headers, "Outra resposta").status_code == 409
    stream = client.get(
        path + "/events",
        headers={**client.operator_headers, "Last-Event-ID": str(first.json()["sequence"])},
    )
    assert stream.status_code == 200
    assert "Olá, " not in stream.text
    assert "mundo!" in stream.text
    assert "event: done" in stream.text
    assert stream.headers["x-accel-buffering"] == "no"
    snapshot = client.get(path, headers=client.operator_headers).json()
    assert snapshot["partial_answer"] == "Olá, mundo!"


def test_cross_run_lease_and_evidence_are_rejected(client, corpus):
    cid = conversation(client, corpus)
    send(client, cid)
    run, headers = claim(client)
    other = dict(headers, **{"X-Run-Token": uuid4().hex})
    assert finish(client, run, other).status_code == 403
    response = client.post(
        "/tools/consultar_processo",
        headers=headers,
        json={**run["context"], "run_id": str(uuid4())},
    )
    assert response.status_code == 403
    response = client.post(
        f"/runs/{run['run_id']}/result",
        headers=headers,
        json={
            "status": "succeeded",
            "answer": "Texto",
            "sources": [{"document_id": "INVENTADO", "chunk_id": "INVENTADO", "page": 1}],
        },
    )
    assert response.status_code == 422


def test_lease_expiration_preserves_partial_and_excludes_failed_memory(client, engine, corpus):
    cid = conversation(client, corpus)
    send(client, cid, "Pergunta interrompida")
    run, headers = claim(client)
    path = f"/runs/{run['run_id']}"
    client.post(
        path + "/events",
        headers=headers,
        json={"event_id": str(uuid4()), "kind": "text_delta", "text": "Trecho parcial"},
    )
    with engine.begin() as conn:
        conn.execute(update(runs).where(runs.c.run_id == run["run_id"]).values(lease_until=0))
    status = client.get(path, headers=client.operator_headers).json()
    assert status["status"] == "timed_out"
    assert status["partial_answer"] == "Trecho parcial"
    assert client.post(path + "/heartbeat", headers=headers).status_code == 409
    assert send(client, cid, "Nova pergunta").status_code == 202
    next_run, _ = claim(client)
    assert next_run["history"] == [{"role": "user", "content": "Nova pergunta"}]


def test_context_limit_does_not_silently_truncate(client, corpus):
    cid = conversation(client, corpus)
    client.app.state.execution.context_limit = 5
    response = send(client, cid, "Pergunta maior que o contexto")
    assert response.status_code == 422
    assert response.json()["code"] == "context_limit"
    stored = client.get(f"/conversations/{cid}", headers=client.operator_headers).json()
    assert stored["messages"] == []


@pytest.mark.parametrize("tool", ["salvar_minuta", "registrar_pendencia"])
def test_writes_are_idempotent_and_independently_readable(client, corpus, engine, tool):
    cid = conversation(client, corpus)
    send(client, cid)
    run, headers = claim(client)
    evidence = {
        "kind": "inventory",
        "process_id": corpus[0].process_id,
        "corpus_version": corpus[0].corpus_version,
    }
    data = {
        **run["context"],
        "idempotency_key": "occurrence-1",
        "content": "Conteúdo fictício",
        "evidence": [evidence],
        "evidence_note": "Exportação parcial; conferir inventário.",
    }
    if tool == "registrar_pendencia":
        data["requirement_id"] = "REQ-DEMO-001"
    first = client.post(f"/tools/{tool}", headers=headers, json=data)
    assert first.status_code == 200, first.text
    replay = client.post(f"/tools/{tool}", headers=headers, json=data)
    assert replay.json()["artifact_id"] == first.json()["artifact_id"]
    assert replay.json()["replayed"] is True
    assert (
        client.post(
            f"/tools/{tool}", headers=headers, json={**data, "content": "Conteúdo diferente"}
        ).status_code
        == 409
    )
    artifact_id = first.json()["artifact_id"]
    stored = client.get(f"/artifacts/{artifact_id}", headers=client.operator_headers)
    assert stored.status_code == 200
    assert stored.json()["payload"]["content"] == data["content"]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == run["run_id"])
            ).scalar_one()
            == 1
        )


def test_concurrent_write_and_invalid_evidence_rollback(client, corpus, engine):
    cid = conversation(client, corpus)
    send(client, cid)
    run, headers = claim(client)
    data = {
        **run["context"],
        "idempotency_key": "concurrent",
        "content": "Minuta fictícia",
        "evidence": [
            {"kind": "inventory", **{k: scope(corpus)[k] for k in ("process_id", "corpus_version")}}
        ],
        "evidence_note": "Base parcial.",
    }
    bad = {**data, "evidence": [{"document_id": "fake", "chunk_id": "fake", "page": 1}]}
    assert client.post("/tools/salvar_minuta", headers=headers, json=bad).status_code == 422
    with engine.connect() as conn:
        assert (
            conn.execute(select(artifacts).where(artifacts.c.run_id == run["run_id"])).first()
            is None
        )

    def write(_):
        return client.post("/tools/salvar_minuta", headers=headers, json=data)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(write, range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["artifact_id"] for r in responses}) == 1


def test_readonly_profile_and_other_owner_cannot_write_or_read(client, corpus, engine):
    token = uuid4().hex
    grants = [(corpus[0].process_id, corpus[0].corpus_version)]
    provision(engine, "reader-" + uuid4().hex, token, "operator", grants)
    other_headers = {"Authorization": "Bearer " + token}
    cid = conversation(client, corpus)
    assert client.get(f"/conversations/{cid}", headers=other_headers).status_code == 404
    own = client.post("/conversations", headers=other_headers, json=scope(corpus)).json()
    response = client.post(
        f"/conversations/{own['conversation_id']}/messages",
        headers=other_headers,
        json={"content": "Uma pergunta", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == 202
    run, headers = claim(client)
    response = client.post(
        "/tools/salvar_minuta",
        headers=headers,
        json={
            **run["context"],
            "content": "Texto",
            "idempotency_key": "readonly",
            "evidence": [
                {
                    "kind": "inventory",
                    "process_id": corpus[0].process_id,
                    "corpus_version": corpus[0].corpus_version,
                }
            ],
            "evidence_note": "Parcial",
        },
    )
    assert response.status_code == 403


def test_simulation_worker_end_to_end(client, corpus):
    cid = conversation(client, corpus)
    send(client, cid)
    run, _ = claim(client)

    async def consume():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            headers=client.worker_headers,
        ) as http:
            await execute(http, ClaimedRun.model_validate(run), SimulationAdapter())

    asyncio.run(consume())
    stored = client.get(f"/conversations/{cid}", headers=client.operator_headers).json()
    assert [m["role"] for m in stored["messages"]] == ["user", "assistant"]
    assert "nenhuma LLM" in stored["messages"][-1]["content"]
    assert stored["runs"][0]["status"] == "succeeded"
    assert stored["runs"][0]["result"]["sources"]


def test_storage_failure_rolls_back_artifact_and_returns_safe_error(
    client, corpus, engine, monkeypatch
):
    cid = conversation(client, corpus)
    send(client, cid)
    run, headers = claim(client)

    def broken_event(*args, **kwargs):
        raise SQLAlchemyError("sensitive_sql_must_not_be_returned")

    monkeypatch.setattr(client.app.state.execution, "event", broken_event)
    response = client.post(
        "/tools/salvar_minuta",
        headers=headers,
        json={
            **run["context"],
            "idempotency_key": "rollback",
            "content": "Minuta fictícia",
            "evidence": [
                {
                    "kind": "inventory",
                    "process_id": corpus[0].process_id,
                    "corpus_version": corpus[0].corpus_version,
                }
            ],
            "evidence_note": "Exportação parcial.",
        },
    )
    assert response.status_code == 503
    assert response.json()["retryable"] is True
    assert "sensitive_sql" not in response.text
    with engine.connect() as conn:
        assert (
            conn.execute(select(artifacts).where(artifacts.c.run_id == run["run_id"])).first()
            is None
        )

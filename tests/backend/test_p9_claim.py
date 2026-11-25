"""P9b: um claim em andamento não esconde o resto da fila de outro worker.

Antes, o SELECT do claim travava (``FOR UPDATE SKIP LOCKED``) todos os runs na fila do
executor durante a transação; um segundo worker pulava todos e recebia 204 com trabalho na
fila. No SQLite as transações de escrita são serializadas (``BEGIN IMMEDIATE``), então o teste
só distingue antes e depois no PostgreSQL; nos dois bancos ele confere que cada worker recebe um
run diferente.
"""

import threading
import time
from uuid import uuid4

from services.backend.auth import authenticate, provision


def queue(client, corpus, count):
    process, _ = corpus
    scope = {
        "process_id": process.process_id,
        "corpus_version": process.corpus_version,
        "requirements_version": process.requirements_version,
    }
    for _ in range(count):
        response = client.post(
            "/runs",
            headers=client.operator_headers,
            json={**scope, "task": "Fila", "task_id": "DEV-001", "idempotency_key": str(uuid4())},
        )
        assert response.status_code == 202, response.text


def test_second_worker_claims_while_first_claim_is_open(client, corpus, engine, monkeypatch):
    process, _ = corpus
    queue(client, corpus, 2)
    token = uuid4().hex
    grants = [(process.process_id, process.corpus_version)]
    provision(
        engine,
        "worker-b-" + uuid4().hex,
        token,
        "worker",
        grants,
        can_write=True,
        executor="simulation",
    )
    first = authenticate(engine, client.worker_headers["Authorization"])
    second = authenticate(engine, "Bearer " + token)
    service = client.app.state.execution
    original = service.event
    holding, release = threading.Event(), threading.Event()

    def slow_event(conn, run_id, kind, payload, event_id=None):
        # O primeiro claim segura a transação aberta depois de reservar o seu run.
        if kind == "status" and not holding.is_set():
            holding.set()
            release.wait(10)
        return original(conn, run_id, kind, payload, event_id)

    monkeypatch.setattr(service, "event", slow_event)
    results = {}
    worker_a = threading.Thread(
        target=lambda: results.__setitem__("a", service.claim(first, "simulation"))
    )
    worker_a.start()
    assert holding.wait(10)
    worker_b = threading.Thread(
        target=lambda: results.__setitem__("b", service.claim(second, "simulation"))
    )
    worker_b.start()
    if engine.dialect.name == "postgresql":
        worker_b.join(10)
        release.set()
    else:
        # SQLite: B espera a transação de A; liberar A deixa B continuar.
        time.sleep(0.5)
        release.set()
        worker_b.join(10)
    worker_a.join(10)
    assert results.get("a") and results.get("b"), results
    assert results["a"]["run_id"] != results["b"]["run_id"]

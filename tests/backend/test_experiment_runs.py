"""/experiments na v0.2: testes do task/langgraph-grafo (856ff06, João Enomoto) e regras novas.

Os quatro primeiros são os do original. Mudanças necessárias: o executor é o do worker do
fixture (simulation), as chamadas vão com token e reserva, e a revisão 2 declara uma chamada
de tool feita de fato, porque o servidor confere o registro com o histórico.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import update

from contracts.models import ExperimentRun, ToolCallRecord
from services.backend.schema import runs


def make_run(context, *, revision=1, latency_ms=10, tool_calls=None, **changes):
    values = dict(
        **context,
        task_id="DEV-001",
        split="development",
        executor="simulation",
        repetition=1,
        code_commit="test-commit",
        harness_version="test-harness",
        adapter_version="test-adapter",
        model="synthetic-test-model",
        endpoint_id="synthetic-endpoint",
        prompt_sha256="0" * 64,
        parameters={"level": "chained", "status": "completed", "revision": revision},
        started_at=datetime(2026, 11, 18, tzinfo=UTC),
        latency_ms=latency_ms,
        tool_calls=tool_calls or [],
        agent_declared_success=True,
        persisted_artifact_ids=[],
        verified_success=None,
        evaluator=None,
    )
    return ExperimentRun(**{**values, **changes})


def body(run):
    return run.model_dump(mode="json")


def real_call(client, context, call_id="tool-1"):
    response = client.post(
        "/tools/consultar_processo", headers={"X-Tool-Call-Id": call_id}, json=context
    )
    assert response.status_code == 200, response.text
    return ToolCallRecord(
        tool_call_id=call_id, tool="consultar_processo", duration_ms=4, status="ok"
    )


# --- Testes do original (856ff06) -------------------------------------------------------


def test_experiment_run_is_persisted_idempotently_and_read_back(client, context):
    run = make_run(context)

    created = client.post("/experiments", json=body(run))
    replay = client.post("/experiments", json=body(run))
    read = client.get(f"/experiments/{run.run_id}")

    assert created.status_code == 200, created.text
    assert replay.status_code == 200
    assert read.status_code == 200
    assert ExperimentRun.model_validate(read.json()) == run
    assert len(client.get(f"/experiments/{run.run_id}/revisions").json()) == 1


def test_experiment_run_conflict_and_sequential_revision_history(client, context):
    run = make_run(context)
    assert client.post("/experiments", json=body(run)).status_code == 200

    changed_same_revision = run.model_copy(update={"latency_ms": 11})
    conflict = client.post("/experiments", json=body(changed_same_revision))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"

    next_run = make_run(context, revision=2, latency_ms=25, tool_calls=[real_call(client, context)])
    updated = client.put(f"/experiments/{run.run_id}", json=body(next_run))
    history = client.get(f"/experiments/{run.run_id}/revisions")

    assert updated.status_code == 200, updated.text
    assert ExperimentRun.model_validate(updated.json()) == next_run
    assert [item["parameters"]["revision"] for item in history.json()] == [1, 2]


def test_experiment_update_rejects_identity_change(client, context):
    run = make_run(context)
    client.post("/experiments", json=body(run))
    wrong_identity = run.model_copy(
        update={
            "parameters": {"level": "chained", "status": "completed", "revision": 2},
            "model": "outro-modelo",
        }
    )
    response = client.put(f"/experiments/{run.run_id}", json=body(wrong_identity))
    assert response.status_code == 409


def test_experiment_update_cannot_change_level_or_reduce_metrics(client, context):
    run = make_run(context)
    client.post("/experiments", json=body(run))
    for parameters, latency in [
        ({"level": "resumable", "status": "completed", "revision": 2}, 25),
        ({"level": "chained", "status": "completed", "revision": 2}, 5),
    ]:
        changed = run.model_copy(update={"parameters": parameters, "latency_ms": latency})
        response = client.put(f"/experiments/{run.run_id}", json=body(changed))
        assert response.status_code == 409


# --- Regras acrescentadas na v0.2 -------------------------------------------------------


def test_reads_and_writes_require_credentials(client, context):
    run = make_run(context)
    anonymous = {"Authorization": "", "X-Run-Token": ""}
    assert client.post("/experiments", json=body(run), headers=anonymous).status_code == 401
    assert client.post("/experiments", json=body(run)).status_code == 200
    assert client.get(f"/experiments/{run.run_id}", headers=anonymous).status_code == 401
    # Operador dono do run lê, mas não escreve.
    operator = {**client.operator_headers, "X-Run-Token": ""}
    assert client.get(f"/experiments/{run.run_id}", headers=operator).status_code == 200
    assert client.get(f"/experiments/{run.run_id}/revisions", headers=operator).json()
    assert client.post("/experiments", json=body(run), headers=operator).status_code == 403


def test_write_requires_this_runs_lease(client, context):
    run = make_run(context)
    wrong_lease = client.post("/experiments", json=body(run), headers={"X-Run-Token": "x"})
    assert wrong_lease.status_code == 403
    other_run = make_run({**context, "run_id": str(uuid4())})
    assert client.post("/experiments", json=body(other_run)).status_code == 403


def test_record_must_match_reserved_scope(client, context):
    for changes in [{"task_id": "DEV-999"}, {"executor": "langgraph"}, {"evaluator": "alguém"}]:
        response = client.post("/experiments", json=body(make_run(context, **changes)))
        assert response.status_code == 422, (changes, response.text)


def test_declared_tool_calls_must_match_server_history(client, context):
    invented = ToolCallRecord(
        tool_call_id="tool-inventada", tool="consultar_processo", duration_ms=1, status="ok"
    )
    response = client.post("/experiments", json=body(make_run(context, tool_calls=[invented])))
    assert response.status_code == 422
    real_call(client, context, "tool-real")
    # Com uma chamada no histórico, omitir a declaração também é recusado.
    assert client.post("/experiments", json=body(make_run(context))).status_code == 422


def test_unknown_record_and_expired_lease(client, context, engine):
    run = make_run(context)
    missing = client.get(f"/experiments/{run.run_id}")
    assert missing.status_code == 404 and missing.json()["code"] == "not_found"
    assert client.get(f"/experiments/{run.run_id}/revisions").json() == []
    with engine.begin() as conn:
        conn.execute(
            update(runs).where(runs.c.run_id == str(run.run_id)).values(lease_until=time.time() - 1)
        )
    assert client.post("/experiments", json=body(run)).status_code == 409


def test_result_must_equal_latest_revision(client, context):
    run = make_run(context)
    assert client.post("/experiments", json=body(run)).status_code == 200
    base = {"status": "succeeded", "answer": "Resposta fictícia"}
    different = make_run(context, latency_ms=99)
    response = client.post(
        f"/runs/{run.run_id}/result", json={**base, "experiment": body(different)}
    )
    assert response.status_code == 422, response.text
    accepted = client.post(f"/runs/{run.run_id}/result", json={**base, "experiment": body(run)})
    assert accepted.status_code == 200, accepted.text
    # Run encerrado: reenvio idêntico continua aceito; revisão nova não.
    assert client.post("/experiments", json=body(run)).status_code == 200
    late = make_run(context, revision=2, latency_ms=20)
    assert client.put(f"/experiments/{run.run_id}", json=body(late)).status_code == 409


def test_concurrent_first_writes_keep_one_record(client, context):
    run = make_run(context)
    with ThreadPoolExecutor(4) as pool:
        statuses = list(
            pool.map(lambda _: client.post("/experiments", json=body(run)).status_code, range(4))
        )
    assert statuses == [200, 200, 200, 200]
    assert len(client.get(f"/experiments/{run.run_id}/revisions").json()) == 1


def test_migration_0010_is_additive_and_does_not_invent_records(client, context, engine):
    from sqlalchemy import func, inspect, select

    from services.backend.migrate import migrate

    run = make_run(context)
    assert client.post("/experiments", json=body(run)).status_code == 200
    with engine.connect() as conn:
        before = conn.execute(select(func.count()).select_from(runs)).scalar_one()
    migrate(engine, "0009", downgrade=True)
    names = set(inspect(engine).get_table_names())
    assert {"experiment_runs", "experiment_run_revisions"}.isdisjoint(names)
    migrate(engine)
    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(runs)).scalar_one() == before
    # Upgrade não reconstrói registros: o run continua sem revisão até o worker gravar de novo.
    assert client.get(f"/experiments/{run.run_id}/revisions").json() == []
    assert client.post("/experiments", json=body(run)).status_code == 200


def test_export_includes_revisions_without_free_form_parameters(client, context, engine):
    from scripts.export_chat import records

    run = make_run(context)
    client.post("/experiments", json=body(run))
    final = make_run(context, revision=2, latency_ms=25, tool_calls=[real_call(client, context)])
    assert client.put(f"/experiments/{run.run_id}", json=body(final)).status_code == 200
    done = client.post(
        f"/runs/{run.run_id}/result",
        json={"status": "succeeded", "answer": "Resposta fictícia", "experiment": body(final)},
    )
    assert done.status_code == 200, done.text
    with engine.connect() as conn:
        (item,) = records(conn, run_id=run.run_id, kind="benchmark")
        (full,) = records(conn, run_id=run.run_id, kind="benchmark", include_content=True)
    revisions = item["declared"]["experiment_revisions"]
    assert [r["revision"] for r in revisions] == [1, 2]
    assert revisions[-1]["experiment"] == item["declared"]["experiment"]
    assert "parameters" not in revisions[-1]["experiment"]
    assert [p["revision"] for p in full["content"]["revision_parameters"]] == [1, 2]


def test_failed_run_exports_revisions_with_null_declared_experiment(client, context, engine):
    """Documenta o caso que a Metodologia precisa tratar: revisões gravadas e falha sem registro."""
    from scripts.export_chat import records

    run = make_run(context)
    assert client.post("/experiments", json=body(run)).status_code == 200
    failed = client.post(
        f"/runs/{run.run_id}/result", json={"status": "failed", "error_code": "adapter_error"}
    )
    assert failed.status_code == 200, failed.text
    with engine.connect() as conn:
        (item,) = records(conn, run_id=run.run_id, kind="benchmark")
    assert [r["revision"] for r in item["declared"]["experiment_revisions"]] == [1]
    assert item["declared"]["experiment"] is None


# --- Revisão de 21/11 ----------------------------------------------------------------


def test_record_without_revision_is_revision_one_for_result_and_client(client, context):
    from contextlib import nullcontext

    from agents.interface import ExperimentRunClient

    run = make_run(context)
    run = run.model_copy(update={"parameters": {"level": "chained", "status": "completed"}})
    # O cliente relê o registro com revision=1 acrescentado pelo servidor e não acusa divergência.
    recorder = ExperimentRunClient("http://testserver")
    recorder._client = lambda: nullcontext(client)
    saved = recorder.save(run)
    assert saved.parameters["revision"] == 1
    # O relatório original (sem revision) equivale à revisão 1 gravada.
    response = client.post(
        f"/runs/{run.run_id}/result",
        json={"status": "succeeded", "answer": "Resposta fictícia", "experiment": body(run)},
    )
    assert response.status_code == 200, response.text


def test_worker_without_grant_gets_404_not_403(client, context, engine):
    from services.backend.auth import provision

    run = make_run(context)
    assert client.post("/experiments", json=body(run)).status_code == 200
    token = uuid4().hex
    provision(engine, "worker-sem-concessao", token, "worker", [], executor="simulation")
    response = client.get(
        f"/experiments/{run.run_id}", headers={"Authorization": "Bearer " + token}
    )
    assert response.status_code == 404 and response.json()["code"] == "not_found"

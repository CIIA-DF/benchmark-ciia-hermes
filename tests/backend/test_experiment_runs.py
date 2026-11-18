from datetime import UTC, datetime

from contracts.models import ExperimentRun, ToolCallRecord


def make_run(context, *, revision=1, latency_ms=10, tool_calls=None):
    return ExperimentRun(
        **context,
        task_id="DEV-001",
        split="development",
        executor="langgraph",
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


def test_experiment_run_is_persisted_idempotently_and_read_back(client, context):
    run = make_run(context)

    created = client.post("/experiments", json=run.model_dump(mode="json"))
    replay = client.post("/experiments", json=run.model_dump(mode="json"))
    read = client.get(f"/experiments/{run.run_id}")

    assert created.status_code == 200
    assert replay.status_code == 200
    assert read.status_code == 200
    assert ExperimentRun.model_validate(read.json()) == run
    assert len(client.get(f"/experiments/{run.run_id}/revisions").json()) == 1


def test_experiment_run_conflict_and_sequential_revision_history(client, context):
    run = make_run(context)
    assert client.post("/experiments", json=run.model_dump(mode="json")).status_code == 200

    changed_same_revision = run.model_copy(update={"latency_ms": 11})
    conflict = client.post("/experiments", json=changed_same_revision.model_dump(mode="json"))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "idempotency_conflict"

    next_run = make_run(
        context,
        revision=2,
        latency_ms=25,
        tool_calls=[
            ToolCallRecord(
                tool_call_id="tool-1", tool="consultar_processo", duration_ms=4, status="ok"
            )
        ],
    )
    updated = client.put(f"/experiments/{run.run_id}", json=next_run.model_dump(mode="json"))
    history = client.get(f"/experiments/{run.run_id}/revisions")

    assert updated.status_code == 200
    assert ExperimentRun.model_validate(updated.json()) == next_run
    assert [item["parameters"]["revision"] for item in history.json()] == [1, 2]


def test_experiment_update_rejects_identity_change(client, context):
    run = make_run(context)
    client.post("/experiments", json=run.model_dump(mode="json"))
    wrong_identity = run.model_copy(
        update={
            "parameters": {"level": "chained", "status": "completed", "revision": 2},
            "task_id": "DEV-002",
        }
    )
    response = client.put(f"/experiments/{run.run_id}", json=wrong_identity.model_dump(mode="json"))
    assert response.status_code == 409


def test_experiment_update_cannot_change_level_or_reduce_metrics(client, context):
    run = make_run(context)
    client.post("/experiments", json=run.model_dump(mode="json"))
    for parameters, latency in [
        ({"level": "resumable", "status": "completed", "revision": 2}, 25),
        ({"level": "chained", "status": "completed", "revision": 2}, 5),
    ]:
        changed = run.model_copy(update={"parameters": parameters, "latency_ms": latency})
        response = client.put(f"/experiments/{run.run_id}", json=changed.model_dump(mode="json"))
        assert response.status_code == 409

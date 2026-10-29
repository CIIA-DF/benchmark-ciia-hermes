import json
from uuid import UUID

import pytest

from contracts.models import ExperimentRun
from evaluation.metrics import load_runs, summarize
from evaluation.runner import load_tasks, run_simulation


def test_runner_writes_valid_simulated_records(tmp_path, monkeypatch):
    task = {
        "task_id": "DEV-001",
        "split": "development",
        "corpus_version": "synthetic-v1",
        "requirements_version": "demo-v1",
        "process_id": "PROC-DEMO-001",
        "prompt": "Consultar a previsão.",
    }
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps([task]), encoding="utf-8")
    monkeypatch.setattr("evaluation.runner.TASKS_PATH", tasks_path)
    monkeypatch.setattr("evaluation.runner.repository_state", lambda: ("abc123", True))

    result_paths = run_simulation("development", 2, tmp_path / "results")

    assert len(result_paths) == 2
    records = [
        ExperimentRun.model_validate_json(path.read_text(encoding="utf-8")) for path in result_paths
    ]
    assert len({record.run_id for record in records}) == 2
    assert all(record.executor == "simulation" for record in records)
    assert all(record.verified_success is None for record in records)
    assert all(record.agent_declared_success is False for record in records)
    assert all(record.parameters["working_tree_dirty"] is True for record in records)
    assert all(isinstance(UUID(path.stem), UUID) for path in result_paths)


def test_runner_rejects_split_without_tasks(tmp_path):
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="Nenhuma tarefa"):
        load_tasks(tasks_path, "final")


def test_metrics_keep_unverified_success_and_missing_cost_unknown(tmp_path, monkeypatch):
    task = {
        "task_id": "DEV-001",
        "split": "development",
        "corpus_version": "synthetic-v1",
        "requirements_version": "demo-v1",
        "process_id": "PROC-DEMO-001",
        "prompt": "Consultar a previsão.",
    }
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps([task]), encoding="utf-8")
    from evaluation import runner

    monkeypatch.setattr(runner, "TASKS_PATH", tasks_path)
    monkeypatch.setattr(runner, "repository_state", lambda: ("abc123", False))
    results_dir = tmp_path / "results"
    run_simulation("development", 1, results_dir)

    report = summarize(load_runs(results_dir))

    assert report["run_count"] == 1
    assert report["verified_count"] == 0
    assert report["success_rate"] is None
    assert report["mean_cost_usd"] is None
    assert report["successful_tool_call_rate"] is None

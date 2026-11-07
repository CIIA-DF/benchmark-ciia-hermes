import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from contracts.models import ExperimentRun
from evaluation.metrics import load_runs, summarize
from evaluation.rubric import evaluate_run
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


def test_evaluate_run_across_all_six_pilot_tasks():
    pilot_cases = [
        (
            "DEV-001",
            "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, página 2). "
            "A exportação é parcial e outros anexos podem existir.",
            "A previsão de entrega é janeiro de 2027 (DOC-DEMO-001, página 2). "
            "A exportação é parcial.",
        ),
        (
            "DEV-002",
            "Foi solicitado material didático para oficina experimental (DOC-DEMO-001, p. 1).",
            "Foram solicitados computadores para evento esportivo (DOC-DEMO-001, p. 1).",
        ),
        (
            "DEV-003",
            "O material será utilizado por estudantes durante a atividade (DOC-DEMO-001, p. 1).",
            "O material é para uso exclusivo de professores com verba orçamentária do MEC "
            "(DOC-DEMO-001, p. 1).",
        ),
        (
            "DEV-004",
            "Não foram encontrados pareceres ou edital de licitação em DOC-DEMO-001, p. 2. "
            "A exportação é parcial.",
            "Consta o Parecer nº 55/2026 aprovando a licitação em DOC-DEMO-001, p. 2.",
        ),
        (
            "DEV-005",
            "A página 1 de DOC-DEMO-001 não contém valores monetários ou custos. "
            "A exportação é parcial.",
            "O valor total aprovado é de R$ 25.000,00 na página 1 de DOC-DEMO-001.",
        ),
        (
            "DEV-006",
            "A completude da exportação é parcial e outros anexos podem existir no processo "
            "de origem (DOC-DEMO-001, p. 2).",
            "A exportação é parcial e conclui-se que não existem outros documentos além deste "
            "(DOC-DEMO-001, p. 2).",
        ),
    ]

    for task_id, valid_response, invalid_response in pilot_cases:
        run = ExperimentRun(
            run_id=uuid4(),
            process_id="PROC-DEMO-001",
            corpus_version="synthetic-v1",
            requirements_version="demo-v1",
            task_id=task_id,
            split="development",
            executor="hermes",
            repetition=1,
            code_commit="test-commit",
            harness_version="0.1.0",
            adapter_version="adapter-0.1.0",
            model="test-model",
            endpoint_id="local-test",
            prompt_sha256="0" * 64,
            parameters={},
            started_at=datetime.now(UTC),
            latency_ms=100.0,
            tool_calls=[],
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            agent_declared_success=True,
            persisted_artifact_ids=[],
            verified_success=None,
            evaluator=None,
        )

        eval_valid = evaluate_run(run, response=valid_response)
        assert eval_valid.verified_success is True, f"Falha no cenário de acerto para {task_id}"
        assert eval_valid.evaluator == "deterministic-rubric-v0.1"

        eval_invalid = evaluate_run(run, response=invalid_response)
        assert eval_invalid.verified_success is False, f"Falha no cenário de erro para {task_id}"
        assert eval_invalid.evaluator == "deterministic-rubric-v0.1"

import json
import sys
from uuid import uuid4

from agents.hermes import run as hermes_run
from contracts.models import ExperimentRun, ToolCallRecord, ToolContext


def test_load_evaluation_task_and_context_data():
    task = hermes_run._load_task("DEV-001")

    assert task["prompt"] == (
        "Consulte a previsão de entrega do material didático e informe a fonte "
        "e o limite da exportação."
    )
    assert task["process_id"] == "PROC-DEMO-001"


def test_main_prints_answer_and_experiment_run(monkeypatch, capsys):
    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )
    experiment_run = ExperimentRun(
        **context.model_dump(),
        task_id="DEV-001",
        split="development",
        executor="hermes",
        repetition=1,
        code_commit="test",
        harness_version="0.1.0",
        adapter_version="0.1.0",
        model="model-test",
        endpoint_id="endpoint-test",
        prompt_sha256="a" * 64,
        parameters={"max_tool_rounds": 10},
        started_at="2026-10-27T00:00:00Z",
        latency_ms=123.4,
        tool_calls=[
            ToolCallRecord(
                tool_call_id="call-1",
                tool="ler_documento",
                duration_ms=25,
                status="ok",
            )
        ],
        input_tokens=12,
        output_tokens=3,
        agent_declared_success=True,
        persisted_artifact_ids=[],
        verified_success=None,
        evaluator=None,
    )

    class MockAdapter:
        final_response = "Resposta sintética do agente."

        def run(
            self,
            task,
            supplied_context,
            *,
            task_id="DEV-001",
            split="development",
            repetition=1,
        ):
            assert task.startswith("Consulte a previsão")
            assert supplied_context.process_id == context.process_id
            assert task_id == "DEV-001"
            assert split == "development"
            assert repetition == 1
            return experiment_run

    monkeypatch.setattr(sys, "argv", ["run.py", "--task-id", "DEV-001"])
    monkeypatch.setattr(hermes_run, "HermesAdapter", MockAdapter)

    hermes_run.main()

    output = capsys.readouterr().out
    assert "Resposta sintética do agente." in output
    assert "Resumo da Execução:" in output
    assert f"Run ID: {context.run_id}" in output
    assert "Tokens: 12 in / 3 out" in output
    json_output = output.split("ExperimentRun:\n", maxsplit=1)[1]
    run_data = json.loads(json_output)
    assert run_data["task_id"] == "DEV-001"
    assert run_data["input_tokens"] == 12
    assert run_data["output_tokens"] == 3
    assert run_data["latency_ms"] == 123.4
    assert run_data["tool_calls"][0]["tool"] == "ler_documento"


def test_main_with_custom_arguments_and_save(monkeypatch, tmp_path, capsys):
    task_data = [
        {
            "task_id": "CUSTOM-999",
            "split": "final",
            "corpus_version": "corpus-test",
            "requirements_version": "reqs-test",
            "process_id": "PROC-TEST-001",
            "prompt": "Tarefa de teste customizada.",
        }
    ]
    tasks_file = tmp_path / "evaluation" / "tasks.json"
    tasks_file.parent.mkdir(parents=True, exist_ok=True)
    tasks_file.write_text(json.dumps(task_data, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(hermes_run, "ROOT", tmp_path)
    monkeypatch.setattr(hermes_run, "TASKS_PATH", tasks_file)

    run_id = uuid4()
    context = ToolContext(
        run_id=run_id,
        process_id="PROC-TEST-001",
        corpus_version="corpus-test",
        requirements_version="reqs-test",
    )
    experiment_run = ExperimentRun(
        **context.model_dump(),
        task_id="CUSTOM-999",
        split="final",
        executor="hermes",
        repetition=2,
        code_commit="commit-custom",
        harness_version="0.1.0",
        adapter_version="0.1.0",
        model="model-custom",
        endpoint_id="endpoint-custom",
        prompt_sha256="b" * 64,
        parameters={"max_tool_rounds": 10},
        started_at="2026-10-27T00:00:00Z",
        latency_ms=250.0,
        tool_calls=[],
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.005,
        agent_declared_success=True,
        persisted_artifact_ids=[],
        verified_success=None,
        evaluator=None,
    )

    class MockAdapter:
        final_response = "Execução customizada finalizada."

        def run(
            self,
            task,
            supplied_context,
            *,
            task_id="DEV-001",
            split="development",
            repetition=1,
        ):
            assert task == "Tarefa de teste customizada."
            assert supplied_context.process_id == "PROC-TEST-001"
            assert task_id == "CUSTOM-999"
            assert split == "final"
            assert repetition == 2
            return experiment_run

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run.py",
            "--task-id",
            "CUSTOM-999",
            "--split",
            "final",
            "--repetition",
            "2",
            "--save",
        ],
    )
    monkeypatch.setattr(hermes_run, "HermesAdapter", MockAdapter)

    hermes_run.main()

    output = capsys.readouterr().out
    assert "Execução customizada finalizada." in output
    assert "Resumo da Execução:" in output
    assert f"Run ID: {run_id}" in output
    assert "Custo: 0.005" in output

    saved_file = tmp_path / "evaluation" / "results" / f"{run_id}.json"
    assert saved_file.exists()
    saved_run = json.loads(saved_file.read_text(encoding="utf-8"))
    assert saved_run["task_id"] == "CUSTOM-999"
    assert saved_run["split"] == "final"
    assert saved_run["repetition"] == 2
    assert saved_run["cost_usd"] == 0.005

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

        def run(self, task, supplied_context, *, task_id=None):
            assert task.startswith("Consulte a previsão")
            assert supplied_context.process_id == context.process_id
            assert task_id == "DEV-001"
            return experiment_run

    monkeypatch.setattr(sys, "argv", ["run.py", "--task-id", "DEV-001"])
    monkeypatch.setattr(hermes_run, "HermesAdapter", MockAdapter)

    hermes_run.main()

    output = capsys.readouterr().out
    assert "Resposta sintética do agente." in output
    json_output = output.split("ExperimentRun:\n", maxsplit=1)[1]
    run_data = json.loads(json_output)
    assert run_data["task_id"] == "DEV-001"
    assert run_data["input_tokens"] == 12
    assert run_data["output_tokens"] == 3
    assert run_data["latency_ms"] == 123.4
    assert run_data["tool_calls"][0]["tool"] == "ler_documento"

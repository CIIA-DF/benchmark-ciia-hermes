import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from contracts.models import ExperimentRun, ToolCallRecord, ToolContext
from evaluation.metrics import (
    generate_preliminary_report,
    load_runs,
    paired_comparison,
    save_preliminary_report,
    summarize,
    summarize_by_executor,
)
from evaluation.rubric import (
    TextQualityScore,
    compute_blind_agreement,
    evaluate_rubric,
    prepare_blind_packet,
)
from evaluation.runner import (
    SimulationAdapter,
    build_tool_context,
    load_tasks,
    resolve_adapter,
    run_paired_adapters,
    run_simulation,
)
from evaluation.runner import (
    main as runner_main,
)


def _make_run(
    task_id: str = "DEV-001",
    executor: str = "hermes",
    repetition: int = 1,
    latency_ms: float = 100.0,
    cost_usd: float | None = 0.02,
    verified_success: bool | None = True,
    tool_calls: list[ToolCallRecord] | None = None,
    persisted_artifact_ids: list[str] | None = None,
) -> ExperimentRun:
    ctx = build_tool_context(
        {
            "process_id": "PROC-DEMO-001",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
        }
    )
    return ExperimentRun(
        **ctx.model_dump(),
        task_id=task_id,
        split="development",
        executor=executor,
        repetition=repetition,
        code_commit="abc123",
        harness_version="0.1.0",
        adapter_version="0.1.0",
        model="test-model",
        endpoint_id="local",
        prompt_sha256="0" * 64,
        parameters={},
        started_at=datetime.now(UTC),
        latency_ms=latency_ms,
        tool_calls=tool_calls or [],
        input_tokens=100,
        output_tokens=50,
        cost_usd=cost_usd,
        agent_declared_success=True,
        persisted_artifact_ids=persisted_artifact_ids or [],
        verified_success=verified_success,
        evaluator="EVAL-01" if verified_success is not None else None,
    )


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
    assert report["ctce_usd"] is None
    assert report["successful_tool_call_rate"] is None
    assert report["tool_usage_accuracy"] is None


def test_metrics_computes_sr_tua_and_ctce():
    calls = [
        ToolCallRecord(tool_call_id="c1", tool="consultar_processo", duration_ms=10, status="ok"),
        ToolCallRecord(tool_call_id="c2", tool="buscar_documentos", duration_ms=15, status="error"),
    ]
    r1 = _make_run(task_id="DEV-001", cost_usd=0.04, verified_success=True, tool_calls=calls)
    r2 = _make_run(task_id="DEV-002", cost_usd=0.06, verified_success=False, tool_calls=calls)

    report = summarize([r1, r2])
    assert report["success_rate"] == 0.5
    assert report["tool_usage_accuracy"] == 0.5
    assert report["ctce_usd"] == pytest.approx(0.10)
    assert report["total_tokens"] == 300
    assert report["mean_steps"] == 2.0


def test_paired_adapters_alternate_order_and_isolate_context(tmp_path):
    order_log: list[tuple[str, UUID]] = []

    class FakeAdapter:
        def __init__(self, name: str):
            self.name = name

        def run(self, task: str, context: ToolContext) -> ExperimentRun:
            order_log.append((self.name, context.run_id))
            return _make_run(executor=self.name)

    tasks = [
        {
            "task_id": "DEV-001",
            "split": "development",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
            "process_id": "PROC-DEMO-001",
            "prompt": "Prompt de teste",
        }
    ]
    paths = run_paired_adapters(
        tasks,
        {"hermes": FakeAdapter("hermes"), "langgraph": FakeAdapter("langgraph")},
        repetitions=2,
        results_dir=tmp_path / "paired",
    )
    assert len(paths) == 4
    assert [name for name, _ in order_log] == ["hermes", "langgraph", "langgraph", "hermes"]
    assert len({run_id for _, run_id in order_log}) == 4


def test_paired_comparison_aggregates_by_task_and_runs_tests():
    runs = [
        _make_run(
            task_id="DEV-001",
            executor="hermes",
            repetition=1,
            latency_ms=100,
            verified_success=True,
        ),
        _make_run(
            task_id="DEV-001",
            executor="hermes",
            repetition=2,
            latency_ms=120,
            verified_success=True,
        ),
        _make_run(
            task_id="DEV-001",
            executor="langgraph",
            repetition=1,
            latency_ms=200,
            verified_success=False,
        ),
        _make_run(
            task_id="DEV-001",
            executor="langgraph",
            repetition=2,
            latency_ms=220,
            verified_success=False,
        ),
        _make_run(
            task_id="DEV-002",
            executor="hermes",
            repetition=1,
            latency_ms=150,
            verified_success=True,
        ),
        _make_run(
            task_id="DEV-002",
            executor="langgraph",
            repetition=1,
            latency_ms=260,
            verified_success=True,
        ),
        _make_run(
            task_id="DEV-003",
            executor="hermes",
            repetition=1,
            latency_ms=130,
            verified_success=True,
        ),
        _make_run(
            task_id="DEV-003",
            executor="langgraph",
            repetition=1,
            latency_ms=240,
            verified_success=False,
        ),
    ]
    comp = paired_comparison(runs)
    assert comp["paired_task_count"] == 3
    assert comp["latency_ms"]["t_test"]["mean_diff"] < 0
    assert comp["latency_ms"]["wilcoxon"]["n_non_zero"] == 3
    assert comp["success_rate"]["t_test"]["mean_diff"] > 0


def test_rubric_critical_failure_blocks_verified_success_and_blind_review():
    write_call = ToolCallRecord(
        tool_call_id="w1",
        tool="registrar_pendencia",
        duration_ms=12,
        status="ok",
    )
    run_with_forbidden_write = _make_run(tool_calls=[write_call])
    result = evaluate_rubric(
        run_with_forbidden_write,
        reference_valid=1,
        answer_supported=1,
        completeness_acknowledged=1,
        allow_writes=False,
    )
    assert result.verified_success is False
    assert result.failed_criteria == ["write_policy_respected"]

    clean_run = _make_run(tool_calls=[])
    ok_result = evaluate_rubric(
        clean_run,
        reference_valid=1,
        answer_supported=1,
        completeness_acknowledged=1,
        allow_writes=False,
    )
    assert ok_result.verified_success is True

    packet, key_map = prepare_blind_packet([clean_run], {str(clean_run.run_id): "Resposta."})
    assert len(packet) == 1
    assert "executor" not in packet[0]
    assert key_map[packet[0]["blind_id"]] == str(clean_run.run_id)

    agreement = compute_blind_agreement(
        {"BLIND-0001": 1, "BLIND-0002": 0, "BLIND-0003": 1},
        {"BLIND-0001": 1, "BLIND-0002": 0, "BLIND-0003": 0},
    )
    assert agreement["observed_agreement"] == pytest.approx(2 / 3)
    assert agreement["disagreements"] == ["BLIND-0003"]
    assert agreement["requires_adjudication"] is True


def test_text_quality_score_validation():
    tq = TextQualityScore(clarity=5, terminology=4, grounding=5, structure=4)
    assert tq.mean == 4.5

    with pytest.raises(ValueError, match="Dimensão clarity"):
        TextQualityScore(clarity=6, terminology=4, grounding=5, structure=4)

    with pytest.raises(ValueError, match="Dimensão structure"):
        TextQualityScore(clarity=5, terminology=4, grounding=5, structure=0)


def test_summarize_by_executor_and_report_generation(tmp_path):
    call_ok = ToolCallRecord(
        tool_call_id="c1", tool="consultar_processo", duration_ms=12, status="ok"
    )
    call_err = ToolCallRecord(
        tool_call_id="c2", tool="buscar_documentos", duration_ms=20, status="error"
    )

    r_hermes = [
        _make_run(
            task_id="DEV-001",
            executor="hermes",
            latency_ms=100,
            verified_success=True,
            tool_calls=[call_ok],
        ),
        _make_run(
            task_id="DEV-002",
            executor="hermes",
            latency_ms=150,
            verified_success=True,
            tool_calls=[call_ok, call_err],
        ),
    ]
    r_lg = [
        _make_run(
            task_id="DEV-001",
            executor="langgraph",
            latency_ms=200,
            verified_success=False,
            tool_calls=[call_ok],
        ),
        _make_run(
            task_id="DEV-002",
            executor="langgraph",
            latency_ms=250,
            verified_success=True,
            tool_calls=[call_ok],
        ),
    ]
    all_runs = r_hermes + r_lg

    summary = summarize_by_executor(all_runs)
    assert "hermes" in summary
    assert "langgraph" in summary
    assert summary["hermes"]["run_count"] == 2
    assert summary["hermes"]["success_rate"] == 1.0
    assert summary["hermes"]["mean_latency_ms"] == 125.0
    assert summary["hermes"]["std_latency_ms"] == pytest.approx(35.355, rel=1e-2)
    assert summary["hermes"]["compliance_rate"] == 1.0
    assert summary["hermes"]["input_tokens"]["total"] == 200

    assert summary["langgraph"]["success_rate"] == 0.5
    assert summary["langgraph"]["mean_latency_ms"] == 225.0

    report_dict, md_text = generate_preliminary_report(all_runs)
    assert report_dict["total_runs"] == 4
    assert "Taxa de Sucesso Verificado (SR)" in md_text
    assert "Comparação pareada" in md_text
    assert "hermes" in md_text and "langgraph" in md_text

    json_path, md_path = save_preliminary_report(all_runs, tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    loaded_report = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded_report["total_runs"] == 4


def test_runner_filter_task_ids_and_repeats(tmp_path, monkeypatch):
    tasks = [
        {
            "task_id": "DEV-001",
            "split": "development",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
            "process_id": "PROC-DEMO-001",
            "prompt": "Tarefa 1",
        },
        {
            "task_id": "DEV-002",
            "split": "development",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
            "process_id": "PROC-DEMO-001",
            "prompt": "Tarefa 2",
        },
        {
            "task_id": "DEV-003",
            "split": "development",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
            "process_id": "PROC-DEMO-001",
            "prompt": "Tarefa 3",
        },
    ]
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(json.dumps(tasks), encoding="utf-8")
    monkeypatch.setattr("evaluation.runner.TASKS_PATH", tasks_path)
    monkeypatch.setattr("evaluation.runner.repository_state", lambda: ("hash-commit", False))

    paths = run_simulation(
        "development",
        repetitions=2,
        results_dir=tmp_path / "filtered",
        task_ids=["DEV-001", "DEV-002"],
    )
    # 2 tarefas x 2 repetições = 4 arquivos
    assert len(paths) == 4
    records = [ExperimentRun.model_validate_json(p.read_text(encoding="utf-8")) for p in paths]
    task_ids = {r.task_id for r in records}
    assert task_ids == {"DEV-001", "DEV-002"}


def test_resolve_adapter_simulation_and_missing_real_adapters():
    sim_adapter = resolve_adapter("simulation")
    assert isinstance(sim_adapter, SimulationAdapter)

    ctx = build_tool_context(
        {
            "process_id": "PROC-DEMO-001",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
        }
    )
    run = sim_adapter.run("Prompt simulado", ctx)
    assert run.executor == "simulation"
    assert run.run_id == ctx.run_id

    with pytest.raises(NotImplementedError, match="hermes"):
        resolve_adapter("hermes")

    with pytest.raises(NotImplementedError, match="langgraph"):
        resolve_adapter("langgraph")

    with pytest.raises(ValueError, match="desconhecido"):
        resolve_adapter("inexistente")


def test_runner_main_cli_simulation_and_adapter_handling(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr("evaluation.runner.RESULTS_PATH", tmp_path / "cli_results")
    runner_main(
        [
            "--adapter",
            "simulation",
            "--repeats",
            "1",
            "--task-ids",
            "DEV-001",
            "--results-dir",
            str(tmp_path / "cli_results"),
        ]
    )
    captured = capsys.readouterr()
    assert "Registro simulado" in captured.out

    runner_main(["--adapter", "hermes"])
    captured_hermes = capsys.readouterr()
    assert "AVISO" in captured_hermes.out or "BLOQUEIO" in captured_hermes.out

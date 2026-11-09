"""Testes automatizados para evaluation/export_dashboard.py.

Verifica a construção estruturada do dashboard_payload.json, incluindo:
- Métricas consolidadas e detalhamento por executor e dificuldade
- Testes estatísticos pareados (Wilcoxon e teste t)
- Scores compostos para os 3 perfis metodológicos no intervalo [0.0, 1.0]
- Resumo de tarefas e ordenação do leaderboard
- Exportação em disco e execução via CLI
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from contracts.models import ExperimentRun, ToolCallRecord
from evaluation.export_dashboard import (
    DASHBOARD_PROFILES,
    build_dashboard_payload,
    export_dashboard,
    load_runs_from_directory,
    load_tasks_data,
)
from evaluation.export_dashboard import (
    main as cli_main,
)


def _make_run(
    task_id: str = "DEV-001",
    executor: str = "hermes",
    repetition: int = 1,
    latency_ms: float = 1200.0,
    cost_usd: float | None = 0.025,
    verified_success: bool | None = True,
    agent_declared_success: bool = True,
    model: str = "claude-3-5-sonnet",
    tool_calls: list[ToolCallRecord] | None = None,
) -> ExperimentRun:
    """Gera um ExperimentRun válido para testes em memória."""
    if tool_calls is None:
        tool_calls = [
            ToolCallRecord(
                tool_call_id="call-01",
                tool="consultar_processo",
                duration_ms=200.0,
                status="ok",
            ),
            ToolCallRecord(
                tool_call_id="call-02",
                tool="ler_documento",
                duration_ms=450.0,
                status="ok",
            ),
        ]

    return ExperimentRun(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
        task_id=task_id,
        split="development",
        executor=executor,
        repetition=repetition,
        code_commit="feed001",
        harness_version="0.1.0",
        adapter_version="0.1.0",
        model=model,
        endpoint_id="local:8000",
        prompt_sha256="a" * 64,
        parameters={"temperature": 0.0},
        started_at=datetime.now(UTC),
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        input_tokens=150,
        output_tokens=80,
        cost_usd=cost_usd,
        agent_declared_success=agent_declared_success,
        persisted_artifact_ids=[],
        verified_success=verified_success,
        evaluator="EVAL-RUBRIC-01",
    )


@pytest.fixture
def sample_tasks() -> list[dict]:
    """Lista de tarefas representativas com diferentes níveis de dificuldade."""
    return [
        {
            "task_id": "DEV-001",
            "prompt": "Consulte a previsão de entrega do material didático.",
            "difficulty": "baixa",
            "category": "extracao_direta",
        },
        {
            "task_id": "DEV-002",
            "prompt": "Identifique a fundamentação legal do termo de referência.",
            "difficulty": "baixa",
            "category": "extracao_direta",
        },
        {
            "task_id": "DEV-003",
            "prompt": "Verifique a conformidade da certidão negativa de débitos fiscais.",
            "difficulty": "media",
            "category": "verificacao_requisito",
        },
        {
            "task_id": "DEV-004",
            "prompt": "Audite a cronologia de despachos e aponte divergências temporais.",
            "difficulty": "alta",
            "category": "auditoria_processual",
        },
    ]


@pytest.fixture
def sample_runs() -> list[ExperimentRun]:
    """Conjunto pareado de execuções para hermes, langgraph e simulation."""
    runs: list[ExperimentRun] = []
    # DEV-001 (baixa)
    runs.append(_make_run("DEV-001", "hermes", 1, 1000.0, 0.010, True, True))
    runs.append(_make_run("DEV-001", "hermes", 2, 1100.0, 0.011, True, True))
    runs.append(_make_run("DEV-001", "langgraph", 1, 800.0, 0.009, True, True))
    runs.append(_make_run("DEV-001", "langgraph", 2, 850.0, 0.009, True, True))
    runs.append(_make_run("DEV-001", "simulation", 1, 300.0, None, True, True))

    # DEV-002 (baixa)
    runs.append(_make_run("DEV-002", "hermes", 1, 1200.0, 0.012, True, True))
    runs.append(_make_run("DEV-002", "langgraph", 1, 950.0, 0.010, True, True))

    # DEV-003 (media)
    runs.append(_make_run("DEV-003", "hermes", 1, 2500.0, 0.025, True, True))
    runs.append(_make_run("DEV-003", "langgraph", 1, 2100.0, 0.020, True, True))

    # DEV-004 (alta): hermes falha no verificado mas declara sucesso
    runs.append(_make_run("DEV-004", "hermes", 1, 4500.0, 0.045, False, True))
    runs.append(_make_run("DEV-004", "langgraph", 1, 3800.0, 0.035, True, True))
    return runs


def test_build_dashboard_payload_structure(
    sample_runs: list[ExperimentRun], sample_tasks: list[dict]
):
    """Verifica que todas as seções obrigatórias estão presentes no payload gerado."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)

    # 1. Seções de alto nível
    assert "metadata" in payload
    assert "summary" in payload
    assert "by_executor" in payload
    assert "by_difficulty" in payload
    assert "paired_comparison" in payload
    assert "profiles" in payload
    assert "tasks" in payload
    assert "leaderboard" in payload

    # 2. Metadata
    meta = payload["metadata"]
    assert meta["contract_version"] == "0.1"
    assert meta["total_runs"] == len(sample_runs)
    assert meta["total_tasks"] == len(sample_tasks)
    assert "timestamp" in meta
    assert set(meta["executors"]) == {"hermes", "langgraph", "simulation"}

    # 3. Summary consolidado
    summary = payload["summary"]
    assert summary["run_count"] == len(sample_runs)
    assert summary["verified_count"] == len(sample_runs)
    assert 0.0 <= summary["success_rate"] <= 1.0
    assert summary["latency"]["mean_ms"] > 0
    assert summary["tool_calls"]["total"] > 0
    assert summary["tua"] is not None and 0.0 <= summary["tua"] <= 1.0
    assert summary["cost"]["mean_usd"] is not None


def test_by_executor_metrics(sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica o detalhamento por executor e a distinção entre sucesso declarado e verificado."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    by_exec = payload["by_executor"]

    assert "hermes" in by_exec
    assert "langgraph" in by_exec
    assert "simulation" in by_exec

    hermes = by_exec["hermes"]
    assert hermes["run_count"] == 5
    assert hermes["success_rate"] == 0.8  # 4 sucessos em 5 runs
    assert hermes["agent_declared_success_rate"] == 1.0  # Declarou sucesso em todas
    assert hermes["declared"] > hermes["sr"]  # Premissa: declarado != verificado
    assert hermes["tua"] == 1.0
    assert hermes["mean_latency_ms"] > 0
    assert "composite_scores" in hermes

    lg = by_exec["langgraph"]
    assert lg["run_count"] == 5
    assert lg["success_rate"] == 1.0
    assert lg["mean_latency_ms"] < hermes["mean_latency_ms"]


def test_by_difficulty_metrics(sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica o detalhamento estratificado por nível de dificuldade."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    by_diff = payload["by_difficulty"]

    for level in ("baixa", "media", "alta"):
        assert level in by_diff
        d_info = by_diff[level]
        assert d_info["difficulty"] == level
        assert d_info["run_count"] > 0
        assert 0.0 <= d_info["success_rate"] <= 1.0
        assert "by_executor" in d_info

    # Na dificuldade alta, hermes teve 0% e langgraph 100%
    alta = by_diff["alta"]
    assert alta["by_executor"]["hermes"]["success_rate"] == 0.0
    assert alta["by_executor"]["langgraph"]["success_rate"] == 1.0


def test_paired_comparison_statistics(sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica os testes pareados de Wilcoxon e teste t entre hermes e langgraph."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    paired = payload["paired_comparison"]

    assert paired is not None
    assert paired["executor_a"] == "hermes"
    assert paired["executor_b"] == "langgraph"
    assert paired["paired_task_count"] >= 2

    # Verifica testes em latência e passos
    for dim in ("latency_ms", "steps"):
        dim_data = paired[dim]
        assert "t_test" in dim_data
        assert "wilcoxon" in dim_data
        t_stat = dim_data["t_test"]
        w_stat = dim_data["wilcoxon"]
        assert 0.0 <= t_stat["p_value"] <= 1.0
        assert 0.0 <= w_stat["p_value"] <= 1.0

    # Verifica acesso direto aos p-valores
    p_vals = paired["p_values"]
    assert "latency_t_test" in p_vals
    assert "latency_wilcoxon" in p_vals
    assert 0.0 <= p_vals["latency_t_test"] <= 1.0


def test_profiles_presence_and_score_bounds(
    sample_runs: list[ExperimentRun], sample_tasks: list[dict]
):
    """Verifica que os 3 perfis metodológicos estão presentes com scores entre 0.0 e 1.0."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    profiles = payload["profiles"]

    expected_profiles = ["balanceado", "triagem_operacional", "auditoria_juridica"]
    for p_name in expected_profiles:
        assert p_name in profiles, f"Perfil {p_name} ausente em profiles."
        p_data = profiles[p_name]

        # Score consolidado
        assert "score" in p_data
        score = p_data["score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0, f"Score {score} fora do intervalo [0.0, 1.0] para {p_name}"

        # Pesos metodológicos
        assert "weights" in p_data
        weights = p_data["weights"]
        assert pytest.approx(sum(weights.values()), rel=1e-3) == 1.0

        # Scores por executor
        assert "by_executor" in p_data
        for executor, exec_score in p_data["by_executor"].items():
            assert isinstance(exec_score, float)
            assert 0.0 <= exec_score <= 1.0, (
                f"Score {exec_score} do executor {executor} fora de [0.0, 1.0] no perfil {p_name}"
            )

    # Verifica scores dentro de by_executor
    for _executor, exec_info in payload["by_executor"].items():
        assert "composite_scores" in exec_info
        c_scores = exec_info["composite_scores"]
        for p_name in expected_profiles:
            assert p_name in c_scores
            assert 0.0 <= c_scores[p_name] <= 1.0


def test_profiles_edge_cases():
    """Verifica cálculo dos perfis em cenários de borda (100% sucesso, 0% sucesso, runs vazios)."""
    # 1. Sem runs
    payload_empty = build_dashboard_payload([], [])
    for p_name in DASHBOARD_PROFILES:
        score = payload_empty["profiles"][p_name]["score"]
        assert 0.0 <= score <= 1.0

    # 2. 100% de sucesso e latência mínima
    perfect_runs = [_make_run("DEV-001", "hermes", 1, 50.0, 0.001, True, True)]
    payload_perfect = build_dashboard_payload(perfect_runs, [])
    for p_name in DASHBOARD_PROFILES:
        score = payload_perfect["profiles"][p_name]["score"]
        assert 0.8 <= score <= 1.0

    # 3. 0% de sucesso e latência máxima
    failing_runs = [_make_run("DEV-001", "hermes", 1, 30000.0, 0.10, False, True)]
    payload_failing = build_dashboard_payload(failing_runs, [])
    for p_name in DASHBOARD_PROFILES:
        score = payload_failing["profiles"][p_name]["score"]
        assert 0.0 <= score <= 0.6


def test_tasks_summary(sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica que o resumo das tarefas contém IDs, títulos, dificuldade e SR por executor."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    tasks = payload["tasks"]

    assert len(tasks) == len(sample_tasks)
    t_map = {t["task_id"]: t for t in tasks}

    # DEV-001
    t1 = t_map["DEV-001"]
    assert t1["id"] == "DEV-001"
    assert t1["difficulty"] == "baixa"
    assert t1["category"] == "extracao_direta"
    assert t1["success_rate_by_executor"]["hermes"] == 1.0
    assert t1["success_rate_by_executor"]["langgraph"] == 1.0
    assert t1["success_rate_by_executor"]["simulation"] == 1.0

    # DEV-004
    t4 = t_map["DEV-004"]
    assert t4["difficulty"] == "alta"
    assert t4["success_rate_by_executor"]["hermes"] == 0.0
    assert t4["success_rate_by_executor"]["langgraph"] == 1.0


def test_leaderboard_ordering(sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica que o leaderboard ordena corretamente os executores para exibição no Portal."""
    payload = build_dashboard_payload(sample_runs, sample_tasks)
    leaderboard = payload["leaderboard"]

    assert len(leaderboard) == 2
    assert leaderboard[0]["rank"] == 1
    # LangGraph teve 100% SR e menor latência -> deve ser rank 1
    assert leaderboard[0]["executor"] == "langgraph"
    assert leaderboard[0]["orchestrator"] == "LangGraph"
    assert leaderboard[1]["executor"] == "hermes"
    assert leaderboard[1]["rank"] == 2
    assert leaderboard[0]["steps_label"] != ""
    assert "composite_scores" in leaderboard[0]


def test_export_dashboard_disk_output(
    tmp_path: Path, sample_runs: list[ExperimentRun], sample_tasks: list[dict]
):
    """Verifica exportação em disco do arquivo dashboard_payload.json."""
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)
    out_file = results_dir / "dashboard_payload.json"
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(sample_tasks), encoding="utf-8")

    # Salva algumas execuções individuais no diretório temporário
    for i, r in enumerate(sample_runs):
        run_file = results_dir / f"run_{i}.json"
        run_file.write_text(r.model_dump_json(indent=2), encoding="utf-8")

    loaded_runs = load_runs_from_directory(results_dir)
    assert len(loaded_runs) == len(sample_runs)

    loaded_tasks = load_tasks_data(tasks_file)
    assert len(loaded_tasks) == len(sample_tasks)

    payload, written_path = export_dashboard(
        results_dir=results_dir,
        output_path=out_file,
        tasks_path=tasks_file,
    )

    assert written_path == out_file
    assert out_file.exists()

    # Revalida JSON recarregando do disco
    reloaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert reloaded["metadata"]["total_runs"] == len(sample_runs)
    assert reloaded["metadata"]["total_tasks"] == len(sample_tasks)
    assert reloaded["metadata"]["contract_version"] == "0.1"
    assert "profiles" in reloaded
    assert len(reloaded["leaderboard"]) > 0


def test_cli_execution(tmp_path: Path, sample_runs: list[ExperimentRun], sample_tasks: list[dict]):
    """Verifica a execução completa via interface de linha de comando (CLI)."""
    results_dir = tmp_path / "cli_results"
    results_dir.mkdir(parents=True)
    out_file = results_dir / "custom_dashboard.json"
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(sample_tasks), encoding="utf-8")

    for i, r in enumerate(sample_runs):
        run_file = results_dir / f"run_{i}.json"
        run_file.write_text(r.model_dump_json(indent=2), encoding="utf-8")

    # Executa CLI via função main
    cli_main(
        [
            "--results-dir",
            str(results_dir),
            "--output",
            str(out_file),
            "--tasks-file",
            str(tasks_file),
        ]
    )

    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["metadata"]["total_runs"] == len(sample_runs)
    assert "balanceado" in data["profiles"]


def test_preliminary_report_fallback(tmp_path: Path, sample_tasks: list[dict]):
    """Verifica que o exportador lê relatorio_preliminar.json quando não há runs individuais."""
    results_dir = tmp_path / "report_results"
    results_dir.mkdir(parents=True)
    out_file = results_dir / "dashboard_from_report.json"
    tasks_file = tmp_path / "tasks.json"
    tasks_file.write_text(json.dumps(sample_tasks), encoding="utf-8")

    mock_report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_runs": 12,
        "executors": ["hermes", "langgraph"],
        "by_executor": {
            "hermes": {
                "run_count": 6,
                "verified_count": 6,
                "success_rate": 0.833,
                "mean_latency_ms": 1250.0,
                "mean_steps": 3.5,
                "total_tool_calls": 21,
                "tool_usage_accuracy": 0.95,
                "compliance_rate": 1.0,
                "mean_cost_usd": 0.02,
            },
            "langgraph": {
                "run_count": 6,
                "verified_count": 6,
                "success_rate": 1.0,
                "mean_latency_ms": 950.0,
                "mean_steps": 3.0,
                "total_tool_calls": 18,
                "tool_usage_accuracy": 1.0,
                "compliance_rate": 1.0,
                "mean_cost_usd": 0.018,
            },
        },
        "by_difficulty": {
            "baixa": {"success_rate": 1.0},
            "media": {"success_rate": 0.9},
            "alta": {"success_rate": 0.8},
        },
        "paired_comparison": None,
    }

    report_file = results_dir / "relatorio_preliminar.json"
    report_file.write_text(json.dumps(mock_report), encoding="utf-8")

    payload, _ = export_dashboard(
        results_dir=results_dir,
        output_path=out_file,
        tasks_path=tasks_file,
    )

    assert payload["metadata"]["total_runs"] == 12
    assert "hermes" in payload["by_executor"]
    assert "langgraph" in payload["by_executor"]
    assert payload["profiles"]["balanceado"]["score"] > 0.0

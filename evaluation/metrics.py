"""Resume registros ExperimentRun e executa análise pareada sem tratar null como zero."""

import argparse
import json
import math
from pathlib import Path

from contracts.models import ExperimentRun

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "evaluation" / "results"


def load_runs(results_dir: Path) -> list[ExperimentRun]:
    paths = sorted(results_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"Nenhum registro JSON encontrado em {results_dir}")
    return [ExperimentRun.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]


def summarize(runs: list[ExperimentRun]) -> dict:
    if not runs:
        raise ValueError("Não há execuções para resumir.")

    verified = [run for run in runs if run.verified_success is not None]
    successes = [run for run in verified if run.verified_success is True]
    costs = [run.cost_usd for run in runs if run.cost_usd is not None]
    tokens = [
        (run.input_tokens or 0) + (run.output_tokens or 0)
        for run in runs
        if run.input_tokens is not None or run.output_tokens is not None
    ]
    tool_calls = [call for run in runs for call in run.tool_calls]
    successful_calls = sum(call.status == "ok" for call in tool_calls)

    mean_latency = sum(run.latency_ms for run in runs) / len(runs)
    if len(runs) >= 2:
        variance = sum((run.latency_ms - mean_latency) ** 2 for run in runs) / (len(runs) - 1)
        std_latency: float | None = math.sqrt(variance)
    else:
        std_latency = None

    tua = successful_calls / len(tool_calls) if tool_calls else None
    ctce_usd = sum(costs) / len(successes) if (costs and successes) else None

    return {
        "run_count": len(runs),
        "verified_count": len(verified),
        "success_rate": (len(successes) / len(verified) if verified else None),
        "mean_latency_ms": mean_latency,
        "std_latency_ms": std_latency,
        "mean_steps": len(tool_calls) / len(runs),
        "mean_cost_usd": sum(costs) / len(costs) if costs else None,
        "ctce_usd": ctce_usd,
        "total_tokens": sum(tokens) if tokens else None,
        "tool_call_count": len(tool_calls),
        "successful_tool_call_rate": tua,
        "tool_usage_accuracy": tua,
        "interpretation": ("Simulation records are pipeline checks, not agent evaluation results."),
    }


def _normal_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2.0))


def wilcoxon_signed_rank(diffs: list[float]) -> dict:
    """Teste dos postos sinalizados de Wilcoxon para diferenças pareadas."""
    non_zero = [d for d in diffs if d != 0.0]
    n = len(non_zero)
    if n == 0:
        return {"n_non_zero": 0, "w_stat": 0.0, "p_value": 1.0}

    indexed = sorted(enumerate(non_zero), key=lambda item: abs(item[1]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(indexed[j + 1][1]) == abs(indexed[i][1]):
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1

    w_plus = sum(rank for rank, d in zip(ranks, non_zero, strict=True) if d > 0)
    w_minus = sum(rank for rank, d in zip(ranks, non_zero, strict=True) if d < 0)
    w_stat = min(w_plus, w_minus)

    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0
    if var_w == 0:
        p_val = 1.0
    else:
        z = (w_stat - mean_w) / math.sqrt(var_w)
        p_val = _normal_two_sided_p(z)

    return {"n_non_zero": n, "w_stat": w_stat, "p_value": p_val}


def paired_t_test(diffs: list[float]) -> dict:
    """Teste t pareado e IC 95% sobre diferenças agregadas por tarefa."""
    n = len(diffs)
    if n < 2:
        raise ValueError("Teste pareado exige pelo menos 2 tarefas pareadas.")

    mean_diff = sum(diffs) / n
    variance = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)
    std_diff = math.sqrt(variance)
    se = std_diff / math.sqrt(n)

    if se == 0.0:
        t_stat = 0.0 if mean_diff == 0.0 else math.copysign(math.inf, mean_diff)
        p_val = 1.0 if mean_diff == 0.0 else 0.0
    else:
        t_stat = mean_diff / se
        p_val = _normal_two_sided_p(t_stat)

    margin = 1.96 * se
    return {
        "n_pairs": n,
        "mean_diff": mean_diff,
        "std_diff": std_diff,
        "ci95_low": mean_diff - margin,
        "ci95_high": mean_diff + margin,
        "t_stat": t_stat,
        "p_value": p_val,
    }


def paired_comparison(
    runs: list[ExperimentRun],
    executor_a: str = "hermes",
    executor_b: str = "langgraph",
) -> dict:
    """Compara dois executores agregando repetições por task_id (unidade de análise primária)."""
    by_task_exec: dict[tuple[str, str], list[ExperimentRun]] = {}
    for run in runs:
        if run.executor in (executor_a, executor_b):
            by_task_exec.setdefault((run.task_id, run.executor), []).append(run)

    tasks_a = {task_id for task_id, ex in by_task_exec if ex == executor_a}
    tasks_b = {task_id for task_id, ex in by_task_exec if ex == executor_b}
    shared_tasks = sorted(tasks_a & tasks_b)
    if len(shared_tasks) < 2:
        raise ValueError("São necessárias pelo menos 2 tarefas comuns para comparação pareada.")

    latency_diffs: list[float] = []
    sr_diffs: list[float] = []

    for task_id in shared_tasks:
        group_a = by_task_exec[(task_id, executor_a)]
        group_b = by_task_exec[(task_id, executor_b)]
        lat_a = sum(r.latency_ms for r in group_a) / len(group_a)
        lat_b = sum(r.latency_ms for r in group_b) / len(group_b)
        latency_diffs.append(lat_a - lat_b)

        ver_a = [r.verified_success for r in group_a if r.verified_success is not None]
        ver_b = [r.verified_success for r in group_b if r.verified_success is not None]
        if ver_a and ver_b:
            sr_a = sum(v is True for v in ver_a) / len(ver_a)
            sr_b = sum(v is True for v in ver_b) / len(ver_b)
            sr_diffs.append(sr_a - sr_b)

    return {
        "executor_a": executor_a,
        "executor_b": executor_b,
        "paired_task_count": len(shared_tasks),
        "latency_ms": {
            "t_test": paired_t_test(latency_diffs),
            "wilcoxon": wilcoxon_signed_rank(latency_diffs),
        },
        "success_rate": (
            {
                "t_test": paired_t_test(sr_diffs),
                "wilcoxon": wilcoxon_signed_rank(sr_diffs),
            }
            if len(sr_diffs) >= 2
            else None
        ),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    report = summarize(load_runs(args.results_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

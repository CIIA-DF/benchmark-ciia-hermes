"""Resume registros ExperimentRun e executa análise pareada sem tratar null como zero."""

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

from contracts.models import ExperimentRun
from evaluation.rubric import check_write_policy

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "evaluation" / "results"


def load_runs(results_dir: Path) -> list[ExperimentRun]:
    paths = sorted(results_dir.glob("*.json"))
    # Filtra arquivos especiais de relatório para não misturar com execuções
    record_paths = [p for p in paths if not p.name.startswith("relatorio_")]
    if not record_paths:
        raise ValueError(f"Nenhum registro JSON encontrado em {results_dir}")
    return [
        ExperimentRun.model_validate_json(path.read_text(encoding="utf-8")) for path in record_paths
    ]


def _mean_and_std(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, None
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


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


def summarize_by_executor(runs: list[ExperimentRun]) -> dict[str, dict]:
    """Calcula estatísticas descritivas (média e desvio padrão) detalhadas por executor."""
    grouped: dict[str, list[ExperimentRun]] = {}
    for run in runs:
        grouped.setdefault(run.executor, []).append(run)

    result = {}
    for executor, exec_runs in grouped.items():
        verified = [r for r in exec_runs if r.verified_success is not None]
        successes = [r for r in verified if r.verified_success is True]
        costs = [r.cost_usd for r in exec_runs if r.cost_usd is not None]

        latencies = [r.latency_ms for r in exec_runs]
        mean_lat, std_lat = _mean_and_std(latencies)

        step_counts = [float(len(r.tool_calls)) for r in exec_runs]
        mean_steps, std_steps = _mean_and_std(step_counts)

        all_calls = [c for r in exec_runs for c in r.tool_calls]
        ok_calls = sum(c.status == "ok" for c in all_calls)
        tua = ok_calls / len(all_calls) if all_calls else None

        in_toks = [float(r.input_tokens) for r in exec_runs if r.input_tokens is not None]
        out_toks = [float(r.output_tokens) for r in exec_runs if r.output_tokens is not None]
        tot_toks = [
            float((r.input_tokens or 0) + (r.output_tokens or 0))
            for r in exec_runs
            if r.input_tokens is not None or r.output_tokens is not None
        ]

        mean_in_tok, std_in_tok = _mean_and_std(in_toks)
        mean_out_tok, std_out_tok = _mean_and_std(out_toks)
        mean_tot_tok, std_tot_tok = _mean_and_std(tot_toks)

        # Taxa de conformidade: proporção de execuções sem violação de escrita não autorizada
        compliance_scores = [check_write_policy(r, allow_writes=False) for r in exec_runs]
        compliance_rate = (
            sum(compliance_scores) / len(compliance_scores) if compliance_scores else 1.0
        )

        ctce = sum(costs) / len(successes) if (costs and successes) else None

        result[executor] = {
            "run_count": len(exec_runs),
            "task_count": len({r.task_id for r in exec_runs}),
            "verified_count": len(verified),
            "success_rate": len(successes) / len(verified) if verified else None,
            "mean_latency_ms": mean_lat,
            "std_latency_ms": std_lat,
            "mean_steps": mean_steps,
            "std_steps": std_steps,
            "total_tool_calls": len(all_calls),
            "tool_usage_accuracy": tua,
            "compliance_rate": compliance_rate,
            "input_tokens": {
                "mean": mean_in_tok,
                "std": std_in_tok,
                "total": int(sum(in_toks)) if in_toks else None,
            },
            "output_tokens": {
                "mean": mean_out_tok,
                "std": std_out_tok,
                "total": int(sum(out_toks)) if out_toks else None,
            },
            "total_tokens": {
                "mean": mean_tot_tok,
                "std": std_tot_tok,
                "total": int(sum(tot_toks)) if tot_toks else None,
            },
            "mean_cost_usd": sum(costs) / len(costs) if costs else None,
            "ctce_usd": ctce,
        }
    return result


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
    step_diffs: list[float] = []

    for task_id in shared_tasks:
        group_a = by_task_exec[(task_id, executor_a)]
        group_b = by_task_exec[(task_id, executor_b)]

        lat_a = sum(r.latency_ms for r in group_a) / len(group_a)
        lat_b = sum(r.latency_ms for r in group_b) / len(group_b)
        latency_diffs.append(lat_a - lat_b)

        steps_a = sum(len(r.tool_calls) for r in group_a) / len(group_a)
        steps_b = sum(len(r.tool_calls) for r in group_b) / len(group_b)
        step_diffs.append(steps_a - steps_b)

        ver_a = [r.verified_success for r in group_a if r.verified_success is not None]
        ver_b = [r.verified_success for r in group_b if r.verified_success is not None]
        if ver_a and ver_b:
            sr_a = sum(v is True for v in ver_a) / len(ver_a)
            sr_b = sum(v is True for v in ver_b) / len(ver_b)
            sr_diffs.append(sr_a - sr_b)

    result = {
        "executor_a": executor_a,
        "executor_b": executor_b,
        "paired_task_count": len(shared_tasks),
        "latency_ms": {
            "t_test": paired_t_test(latency_diffs),
            "wilcoxon": wilcoxon_signed_rank(latency_diffs),
        },
        "steps": {
            "t_test": paired_t_test(step_diffs),
            "wilcoxon": wilcoxon_signed_rank(step_diffs),
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
    return result


def _format_metric(val: float | None, fmt: str = ".2f", suffix: str = "") -> str:
    if val is None:
        return "N/D"
    return f"{val:{fmt}}{suffix}"


def _format_mean_std(
    mean: float | None, std: float | None, fmt: str = ".2f", suffix: str = ""
) -> str:
    if mean is None:
        return "N/D"
    if std is None:
        return f"{mean:{fmt}}{suffix}"
    return f"{mean:{fmt}} ± {std:{fmt}}{suffix}"


def generate_preliminary_report(runs: list[ExperimentRun]) -> tuple[dict, str]:
    """Gera dados JSON e relatório em Markdown da rodada piloto comparativa."""
    by_exec = summarize_by_executor(runs)
    executors = sorted(by_exec.keys())

    # Pareamento entre os dois primeiros executores se houver pelo menos dois
    comparison = None
    if len(executors) >= 2:
        try:
            comparison = paired_comparison(runs, executor_a=executors[0], executor_b=executors[1])
        except ValueError:
            comparison = None

    now_iso = datetime.now(UTC).isoformat()
    report_dict = {
        "generated_at": now_iso,
        "total_runs": len(runs),
        "executors": executors,
        "by_executor": by_exec,
        "paired_comparison": comparison,
    }

    # Construção do documento Markdown
    md_lines = [
        "# Relatório Preliminar de Métricas Pareadas — Camada 1",
        "",
        "**Benchmark SEI • CIIA-DF / NIAUnDF • Frente Metodologia (Evaluation)**",
        f"- Data de Geração: `{now_iso}`",
        f"- Total de Execuções Analisadas: `{len(runs)}`",
        f"- Executores Encontrados: {', '.join(f'`{e}`' for e in executors)}",
        "",
        "---",
        "",
        "## 1. Tabela Comparativa Resumo por Executor",
        "",
        "| Métrica | " + " | ".join(f"**{e}**" for e in executors) + " |",
        "| :--- | " + " | ".join(":---:" for _ in executors) + " |",
    ]

    metrics_rows = [
        (
            "Taxa de Sucesso Verificado (SR)",
            lambda d: _format_metric(d["success_rate"], ".1%", ""),
        ),
        (
            "Latência Média (ms)",
            lambda d: _format_mean_std(d["mean_latency_ms"], d["std_latency_ms"], ".1f", " ms"),
        ),
        (
            "Passos Médios (chamadas/tarefa)",
            lambda d: _format_mean_std(d["mean_steps"], d["std_steps"], ".1f"),
        ),
        (
            "Total de Chamadas de Ferramenta",
            lambda d: str(d["total_tool_calls"]),
        ),
        (
            "Acurácia de Ferramentas (TUA)",
            lambda d: _format_metric(d["tool_usage_accuracy"], ".1%"),
        ),
        (
            "Taxa de Conformidade (Políticas)",
            lambda d: _format_metric(d["compliance_rate"], ".1%"),
        ),
        (
            "Consumo Tokens Entrada (méd)",
            lambda d: _format_mean_std(d["input_tokens"]["mean"], d["input_tokens"]["std"], ".0f"),
        ),
        (
            "Consumo Tokens Saída (méd)",
            lambda d: _format_mean_std(
                d["output_tokens"]["mean"], d["output_tokens"]["std"], ".0f"
            ),
        ),
        (
            "Consumo Total de Tokens",
            lambda d: (
                str(d["total_tokens"]["total"]) if d["total_tokens"]["total"] is not None else "N/D"
            ),
        ),
        (
            "Custo Total por Sucesso (CTCE USD)",
            lambda d: _format_metric(d["ctce_usd"], ".4f", " $"),
        ),
    ]

    for label, getter in metrics_rows:
        row_vals = [getter(by_exec[e]) for e in executors]
        md_lines.append(f"| {label} | " + " | ".join(row_vals) + " |")

    md_lines.extend(["", "---", "", "## 2. Análise Estatística Pareada (Wilcoxon e Teste t)"])

    if comparison is not None:
        ea = comparison["executor_a"]
        eb = comparison["executor_b"]
        n_paired = comparison["paired_task_count"]
        md_lines.extend(
            [
                "",
                f"Comparação pareada por tarefa (`{ea}` vs `{eb}`, N={n_paired}):",
                "",
                "| Dimensão | Dif Média (Δ) | IC 95% | Teste t (p-valor) | Wilcoxon W (p) |",
                "| :--- | :---: | :---: | :---: | :---: |",
            ]
        )

        dims = [
            ("Latência (ms)", comparison["latency_ms"]),
            ("Passos (chamadas)", comparison["steps"]),
        ]
        if comparison.get("success_rate"):
            dims.append(("Taxa de Sucesso (SR)", comparison["success_rate"]))

        for dim_name, stat_dict in dims:
            t = stat_dict["t_test"]
            w = stat_dict["wilcoxon"]
            ci_str = f"[{t['ci95_low']:.2f}, {t['ci95_high']:.2f}]"
            t_str = f"t={t['t_stat']:.2f} (p={t['p_value']:.4f})"
            w_str = f"W={w['w_stat']:.1f} (p={w['p_value']:.4f})"
            md_lines.append(
                f"| {dim_name} | {t['mean_diff']:+.2f} | {ci_str} | {t_str} | {w_str} |"
            )
    else:
        md_lines.extend(
            [
                "",
                "> *Nota: Análise pareada exige pelo menos 2 executores com tarefas comuns.*",
                "> *Adaptadores reais pendentes de integração; pipeline em modo de simulação.*",
            ]
        )

    md_lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Conformidade Metodológica e Regras Operacionais",
            "",
            "- **Preservação de Registros**: Valores ausentes ficam como `N/D` (`null`).",
            "- **Unidade de Análise**: Repetições são agregadas por tarefa antes do teste pareado.",
            "- **Transparência**: Registros simulados atestam a estabilidade do pipeline,",
            "  sem simular artificialmente a inteligência dos agentes reais.",
            "",
        ]
    )

    return report_dict, "\n".join(md_lines) + "\n"


def save_preliminary_report(
    runs: list[ExperimentRun],
    results_dir: Path,
) -> tuple[Path, Path]:
    """Exporta o relatório consolidado preliminar em JSON e Markdown."""
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dict, md_text = generate_preliminary_report(runs)

    json_path = results_dir / "relatorio_preliminar.json"
    md_path = results_dir / "relatorio_preliminar.md"

    json_path.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(md_text, encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_PATH)
    parser.add_argument(
        "--generate-report", action="store_true", help="Gera arquivos de relatório JSON e Markdown"
    )
    args = parser.parse_args(argv)

    runs = load_runs(args.results_dir)
    if args.generate_report:
        j_path, m_path = save_preliminary_report(runs, args.results_dir)
        print(f"Relatório preliminar JSON gerado: {j_path}")
        print(f"Relatório preliminar Markdown gerado: {m_path}")
    else:
        report = summarize(runs)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

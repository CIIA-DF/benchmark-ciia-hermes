"""Exportador de dados consolidados para o Portal e Landing Page do Benchmark CIIA.

Gera o payload JSON estruturado (dashboard_payload.json) com métricas consolidadas,
detalhamento por executor, estratificação por dificuldade, comparação estatística pareada,
perfis metodológicos e resumo de tarefas.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts.models import ExperimentRun
from evaluation.metrics import (
    compute_composite_score,
    paired_comparison,
)
from evaluation.rubric import check_write_policy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = ROOT / "evaluation" / "results"
DEFAULT_OUTPUT_PATH = ROOT / "evaluation" / "results" / "dashboard_payload.json"
DEFAULT_TASKS_PATH = ROOT / "evaluation" / "tasks.json"

EXCLUDED_FILE_PREFIXES = ("relatorio_", "preliminary_report", "dashboard_payload")

DASHBOARD_PROFILES: dict[str, dict[str, float]] = {
    "balanceado": {
        "sr": 0.35,
        "compliance": 0.25,
        "tua": 0.15,
        "latency": 0.15,
        "cost": 0.10,
    },
    "triagem_operacional": {
        "sr": 0.20,
        "compliance": 0.20,
        "tua": 0.10,
        "latency": 0.40,
        "cost": 0.10,
    },
    "auditoria_juridica": {
        "sr": 0.40,
        "compliance": 0.40,
        "tua": 0.10,
        "latency": 0.05,
        "cost": 0.05,
    },
}

PROFILE_DESCRIPTIONS: dict[str, str] = {
    "balanceado": (
        "Equilíbrio metodológico entre acurácia factual (35%), conformidade estrita (25%), "
        "acurácia de ferramentas (15%), latência (15%) e custo operacional (10%)."
    ),
    "triagem_operacional": (
        "Otimizado para triagem rápida e alto volume: prioridade em latência (40%), "
        "com sucesso verificado (20%), conformidade (20%), acurácia de ferramentas (10%) "
        "e custo (10%)."
    ),
    "auditoria_juridica": (
        "Rigor processual e documental máximo: ênfase em sucesso verificado (40%) e "
        "conformidade (40%), com acurácia de ferramentas (10%), latência (5%) e custo (5%)."
    ),
}


def _mean_and_std(values: list[float]) -> tuple[float | None, float | None]:
    """Calcula média e desvio padrão amostral."""
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, None
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def load_tasks_data(tasks_path: Path) -> list[dict[str, Any]]:
    """Carrega lista de tarefas a partir de tasks.json."""
    if not tasks_path.exists():
        return []
    try:
        data = json.loads(tasks_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def load_runs_from_directory(results_dir: Path) -> list[ExperimentRun]:
    """Carrega arquivos individuais ExperimentRun de um diretório de resultados."""
    if not results_dir.exists():
        return []
    paths = sorted(results_dir.glob("*.json"))
    record_paths = [
        p for p in paths if not any(p.name.startswith(prefix) for prefix in EXCLUDED_FILE_PREFIXES)
    ]
    runs: list[ExperimentRun] = []
    for p in record_paths:
        try:
            run = ExperimentRun.model_validate_json(p.read_text(encoding="utf-8"))
            runs.append(run)
        except Exception:
            continue
    return runs


def load_preliminary_report(results_dir: Path) -> dict[str, Any] | None:
    """Tenta carregar relatório preliminar JSON se arquivos individuais não existirem."""
    if not results_dir.exists():
        return None
    candidates = [
        results_dir / "relatorio_preliminar.json",
        results_dir / "preliminary_report.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def calculate_metrics_for_runs(runs: list[ExperimentRun]) -> dict[str, Any]:
    """Calcula estatísticas descritivas para uma lista de execuções."""
    if not runs:
        return {
            "run_count": 0,
            "verified_count": 0,
            "success_rate": None,
            "sr": None,
            "agent_declared_success_rate": None,
            "declared": None,
            "latency": {"mean_ms": None, "std_ms": None},
            "mean_latency_ms": None,
            "std_latency_ms": None,
            "tool_calls": {"total": 0, "mean_steps": None},
            "mean_steps": None,
            "std_steps": None,
            "steps": None,
            "tua": None,
            "tool_usage_accuracy": None,
            "compliance_rate": 1.0,
            "cost": {"mean_usd": None, "ctce_usd": None, "total_usd": None},
            "mean_cost_usd": None,
            "ctce_usd": None,
            "ctce": None,
            "total_tokens": None,
        }

    verified = [r for r in runs if r.verified_success is not None]
    successes = [r for r in verified if r.verified_success is True]
    declared = [r for r in runs if r.agent_declared_success is True]
    costs = [r.cost_usd for r in runs if r.cost_usd is not None]

    latencies = [r.latency_ms for r in runs]
    mean_lat, std_lat = _mean_and_std(latencies)

    step_counts = [float(len(r.tool_calls)) for r in runs]
    mean_steps, std_steps = _mean_and_std(step_counts)

    all_calls = [c for r in runs for c in r.tool_calls]
    ok_calls = sum(c.status == "ok" for c in all_calls)
    tua = ok_calls / len(all_calls) if all_calls else None

    compliance_scores = [check_write_policy(r, allow_writes=False) for r in runs]
    compliance_rate = sum(compliance_scores) / len(compliance_scores) if compliance_scores else 1.0

    sr = len(successes) / len(verified) if verified else None
    declared_sr = len(declared) / len(runs) if runs else None
    mean_cost = sum(costs) / len(costs) if costs else None
    total_cost = sum(costs) if costs else None
    ctce = sum(costs) / len(successes) if (costs and successes) else None

    tokens = [
        (r.input_tokens or 0) + (r.output_tokens or 0)
        for r in runs
        if r.input_tokens is not None or r.output_tokens is not None
    ]
    tot_tokens = sum(tokens) if tokens else None

    return {
        "run_count": len(runs),
        "verified_count": len(verified),
        "success_rate": round(sr, 4) if sr is not None else None,
        "sr": round(sr * 100, 2) if sr is not None else None,
        "agent_declared_success_rate": (round(declared_sr, 4) if declared_sr is not None else None),
        "declared": round(declared_sr * 100, 2) if declared_sr is not None else None,
        "latency": {
            "mean_ms": round(mean_lat, 2) if mean_lat is not None else None,
            "std_ms": round(std_lat, 2) if std_lat is not None else None,
        },
        "mean_latency_ms": round(mean_lat, 2) if mean_lat is not None else None,
        "std_latency_ms": round(std_lat, 2) if std_lat is not None else None,
        "tool_calls": {
            "total": len(all_calls),
            "mean_steps": round(mean_steps, 2) if mean_steps is not None else None,
        },
        "mean_steps": round(mean_steps, 2) if mean_steps is not None else None,
        "std_steps": round(std_steps, 2) if std_steps is not None else None,
        "steps": round(mean_steps, 2) if mean_steps is not None else None,
        "tua": round(tua, 4) if tua is not None else None,
        "tool_usage_accuracy": round(tua, 4) if tua is not None else None,
        "compliance_rate": round(compliance_rate, 4),
        "cost": {
            "mean_usd": round(mean_cost, 4) if mean_cost is not None else None,
            "ctce_usd": round(ctce, 4) if ctce is not None else None,
            "total_usd": round(total_cost, 4) if total_cost is not None else None,
        },
        "mean_cost_usd": round(mean_cost, 4) if mean_cost is not None else None,
        "ctce_usd": round(ctce, 4) if ctce is not None else None,
        "ctce": round(ctce, 4) if ctce is not None else None,
        "total_tokens": tot_tokens,
    }


def compute_executor_profiles(metrics: dict[str, Any]) -> dict[str, float]:
    """Calcula os scores compostos para os perfis metodológicos a partir das métricas calculadas."""
    scores: dict[str, float] = {}
    summary_input = {
        "success_rate": metrics.get("success_rate"),
        "compliance_rate": metrics.get("compliance_rate"),
        "tool_usage_accuracy": metrics.get("tua")
        if metrics.get("tua") is not None
        else metrics.get("tool_usage_accuracy"),
        "mean_latency_ms": metrics.get("mean_latency_ms"),
        "mean_cost_usd": metrics.get("mean_cost_usd"),
    }
    for profile_name, weights in DASHBOARD_PROFILES.items():
        score = compute_composite_score(summary_input, profile_or_weights=weights)
        scores[profile_name] = round(score, 4)
    return scores


def build_dashboard_payload(
    runs: list[ExperimentRun],
    tasks: list[dict[str, Any]],
    preliminary_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Constrói o payload JSON completo esperado pelo Portal Next.js e Landing Page."""
    diff_map: dict[str, str] = {
        t["task_id"]: t.get("difficulty", "media") for t in tasks if "task_id" in t
    }

    now_iso = datetime.now(UTC).isoformat()
    total_runs = len(runs)
    total_tasks = len(tasks)

    # Caso 1: Temos execuções individuais reais/simuladas
    if runs:
        summary_metrics = calculate_metrics_for_runs(runs)

        # Agrupamento por executor
        by_exec_grouped: dict[str, list[ExperimentRun]] = {}
        for r in runs:
            by_exec_grouped.setdefault(r.executor, []).append(r)

        by_executor: dict[str, dict[str, Any]] = {}
        for executor, exec_runs in sorted(by_exec_grouped.items()):
            m = calculate_metrics_for_runs(exec_runs)
            m["executor"] = executor
            m["task_count"] = len({r.task_id for r in exec_runs})
            models = {r.model for r in exec_runs if r.model}
            m["model"] = ", ".join(sorted(models)) if models else "N/A"
            prof_scores = compute_executor_profiles(m)
            m["composite_scores"] = prof_scores
            m["profiles"] = prof_scores
            by_executor[executor] = m

        # Agrupamento por dificuldade
        by_difficulty: dict[str, dict[str, Any]] = {}
        for level in ("baixa", "media", "alta"):
            level_runs = [r for r in runs if diff_map.get(r.task_id, "media") == level]
            level_metrics = calculate_metrics_for_runs(level_runs)
            level_metrics["difficulty"] = level
            level_metrics["task_count"] = len({r.task_id for r in level_runs})

            # Detalhamento por executor dentro do nível
            exec_in_level: dict[str, dict[str, Any]] = {}
            for executor in sorted(by_exec_grouped.keys()):
                exec_level_runs = [r for r in level_runs if r.executor == executor]
                if exec_level_runs:
                    elm = calculate_metrics_for_runs(exec_level_runs)
                    exec_in_level[executor] = {
                        "run_count": elm["run_count"],
                        "success_rate": elm["success_rate"],
                        "sr": elm["sr"],
                        "mean_latency_ms": elm["mean_latency_ms"],
                        "mean_steps": elm["mean_steps"],
                        "tua": elm["tua"],
                        "mean_cost_usd": elm["mean_cost_usd"],
                    }
            level_metrics["by_executor"] = exec_in_level
            by_difficulty[level] = level_metrics

        # Comparação pareada
        paired_result: dict[str, Any] | None = None
        executors = sorted(by_executor.keys())
        # Tenta par hermes vs langgraph preferencialmente
        candidate_pairs: list[tuple[str, str]] = []
        if "hermes" in executors and "langgraph" in executors:
            candidate_pairs.append(("hermes", "langgraph"))
        for i in range(len(executors)):
            for j in range(i + 1, len(executors)):
                pair = (executors[i], executors[j])
                if pair not in candidate_pairs:
                    candidate_pairs.append(pair)

        for ea, eb in candidate_pairs:
            try:
                comp = paired_comparison(runs, executor_a=ea, executor_b=eb)
                p_values = {
                    "latency_t_test": comp["latency_ms"]["t_test"]["p_value"],
                    "latency_wilcoxon": comp["latency_ms"]["wilcoxon"]["p_value"],
                    "steps_t_test": comp["steps"]["t_test"]["p_value"],
                    "steps_wilcoxon": comp["steps"]["wilcoxon"]["p_value"],
                    "success_rate_t_test": (
                        comp["success_rate"]["t_test"]["p_value"]
                        if comp.get("success_rate")
                        else None
                    ),
                    "success_rate_wilcoxon": (
                        comp["success_rate"]["wilcoxon"]["p_value"]
                        if comp.get("success_rate")
                        else None
                    ),
                }
                comp["p_values"] = p_values
                paired_result = comp
                break
            except ValueError:
                continue

        # Perfis consolidados
        profiles_payload: dict[str, dict[str, Any]] = {}
        for p_name, weights in DASHBOARD_PROFILES.items():
            overall_score = compute_composite_score(
                {
                    "success_rate": summary_metrics.get("success_rate"),
                    "compliance_rate": summary_metrics.get("compliance_rate"),
                    "tool_usage_accuracy": summary_metrics.get("tua"),
                    "mean_latency_ms": summary_metrics.get("mean_latency_ms"),
                    "mean_cost_usd": summary_metrics.get("mean_cost_usd"),
                },
                profile_or_weights=weights,
            )
            profiles_payload[p_name] = {
                "score": round(overall_score, 4),
                "weights": weights,
                "description": PROFILE_DESCRIPTIONS.get(p_name, ""),
                "by_executor": {e: by_executor[e]["composite_scores"][p_name] for e in by_executor},
            }

        # Resumo de tarefas
        all_executors = sorted(by_executor.keys())
        tasks_summary: list[dict[str, Any]] = []

        # Indexa tarefas conhecidas
        seen_task_ids: set[str] = set()
        for t in tasks:
            tid = t.get("task_id", "")
            seen_task_ids.add(tid)
            prompt = t.get("prompt", "")
            title = t.get("title") or (prompt[:80] + "..." if len(prompt) > 80 else prompt)

            sr_by_exec: dict[str, float | None] = {}
            runs_by_exec: dict[str, int] = {}
            for executor in all_executors:
                e_runs = [r for r in runs if r.task_id == tid and r.executor == executor]
                runs_by_exec[executor] = len(e_runs)
                v_runs = [r for r in e_runs if r.verified_success is not None]
                s_runs = [r for r in v_runs if r.verified_success is True]
                sr_by_exec[executor] = round(len(s_runs) / len(v_runs), 4) if v_runs else None

            tasks_summary.append(
                {
                    "id": tid,
                    "task_id": tid,
                    "title": title,
                    "prompt": prompt,
                    "difficulty": t.get("difficulty", "media"),
                    "category": t.get("category", "geral"),
                    "success_rate": sr_by_exec,
                    "success_rate_by_executor": sr_by_exec,
                    "runs_by_executor": runs_by_exec,
                }
            )

        # Adiciona tarefas encontradas nas execuções que não estavam em tasks.json
        for r in runs:
            if r.task_id not in seen_task_ids:
                seen_task_ids.add(r.task_id)
                sr_by_exec = {}
                runs_by_exec = {}
                for executor in all_executors:
                    e_runs = [
                        item
                        for item in runs
                        if item.task_id == r.task_id and item.executor == executor
                    ]
                    runs_by_exec[executor] = len(e_runs)
                    v_runs = [item for item in e_runs if item.verified_success is not None]
                    s_runs = [item for item in v_runs if item.verified_success is True]
                    sr_by_exec[executor] = round(len(s_runs) / len(v_runs), 4) if v_runs else None

                tasks_summary.append(
                    {
                        "id": r.task_id,
                        "task_id": r.task_id,
                        "title": f"Tarefa {r.task_id}",
                        "prompt": "",
                        "difficulty": diff_map.get(r.task_id, "media"),
                        "category": "desconhecida",
                        "success_rate": sr_by_exec,
                        "success_rate_by_executor": sr_by_exec,
                        "runs_by_executor": runs_by_exec,
                    }
                )

        # Leaderboard ordenado para o portal (agentes reais priorizados sobre simulation)
        leaderboard: list[dict[str, Any]] = []
        candidate_executors = [e for e in by_executor if e != "simulation"] or list(
            by_executor.keys()
        )
        sorted_executors = sorted(
            candidate_executors,
            key=lambda e: (
                by_executor[e]["composite_scores"].get("balanceado", 0.0),
                by_executor[e]["success_rate"] or 0.0,
            ),
            reverse=True,
        )
        for rank, exec_name in enumerate(sorted_executors, start=1):
            ed = by_executor[exec_name]
            orch_name = (
                "Hermes"
                if exec_name == "hermes"
                else ("LangGraph" if exec_name == "langgraph" else exec_name.capitalize())
            )
            lat_sec = (ed["mean_latency_ms"] or 0.0) / 1000.0
            steps_label = f"{ed['mean_steps'] or 0.0:.1f} passos · {lat_sec:.1f}s"
            leaderboard.append(
                {
                    "rank": rank,
                    "executor": exec_name,
                    "orchestrator": orch_name,
                    "model": ed.get("model", "N/A"),
                    "sr": ed.get("sr"),
                    "success_rate": ed.get("success_rate"),
                    "declared": ed.get("declared"),
                    "tua": round((ed.get("tua") or 0.0) * 100, 1)
                    if ed.get("tua") is not None
                    else None,
                    "tool_usage_accuracy": ed.get("tool_usage_accuracy"),
                    "steps": ed.get("mean_steps"),
                    "steps_label": steps_label,
                    "ctce": ed.get("ctce"),
                    "ctce_usd": ed.get("ctce_usd"),
                    "composite_scores": ed.get("composite_scores"),
                }
            )

    # Caso 2: Sem runs individuais, mas temos preliminary_data (relatório preliminar)
    elif preliminary_data:
        by_exec_raw = preliminary_data.get("by_executor", {})
        total_runs = preliminary_data.get("total_runs", 0)

        by_executor = {}
        for executor, edata in by_exec_raw.items():
            m = dict(edata)
            m["executor"] = executor
            prof_scores = compute_executor_profiles(m)
            m["composite_scores"] = prof_scores
            m["profiles"] = prof_scores
            if "success_rate" in m and m["success_rate"] is not None:
                m["sr"] = round(m["success_rate"] * 100, 2)
            if "mean_steps" in m:
                m["steps"] = m["mean_steps"]
            by_executor[executor] = m

        summary_metrics = {
            "run_count": total_runs,
            "verified_count": sum(e.get("verified_count", 0) for e in by_executor.values()),
            "success_rate": (
                sum(e.get("success_rate", 0) or 0 for e in by_executor.values()) / len(by_executor)
                if by_executor
                else None
            ),
            "latency": {
                "mean_ms": (
                    sum(e.get("mean_latency_ms", 0) or 0 for e in by_executor.values())
                    / len(by_executor)
                    if by_executor
                    else None
                ),
                "std_ms": None,
            },
            "tool_calls": {
                "total": sum(e.get("total_tool_calls", 0) for e in by_executor.values()),
                "mean_steps": (
                    sum(e.get("mean_steps", 0) or 0 for e in by_executor.values())
                    / len(by_executor)
                    if by_executor
                    else None
                ),
            },
            "tua": (
                sum(e.get("tool_usage_accuracy", 0) or 0 for e in by_executor.values())
                / len(by_executor)
                if by_executor
                else None
            ),
            "compliance_rate": 1.0,
            "cost": {
                "mean_usd": (
                    sum(e.get("mean_cost_usd", 0) or 0 for e in by_executor.values())
                    / len(by_executor)
                    if by_executor
                    else None
                ),
                "ctce_usd": None,
            },
        }

        by_difficulty = preliminary_data.get("by_difficulty", {})
        paired_result = preliminary_data.get("paired_comparison")

        profiles_payload = {}
        for p_name, weights in DASHBOARD_PROFILES.items():
            overall_score = compute_composite_score(
                {
                    "success_rate": summary_metrics.get("success_rate"),
                    "compliance_rate": summary_metrics.get("compliance_rate"),
                    "tool_usage_accuracy": summary_metrics.get("tua"),
                    "mean_latency_ms": summary_metrics.get("latency", {}).get("mean_ms"),
                    "mean_cost_usd": summary_metrics.get("cost", {}).get("mean_usd"),
                },
                profile_or_weights=weights,
            )
            profiles_payload[p_name] = {
                "score": round(overall_score, 4),
                "weights": weights,
                "description": PROFILE_DESCRIPTIONS.get(p_name, ""),
                "by_executor": {e: by_executor[e]["composite_scores"][p_name] for e in by_executor},
            }

        tasks_summary = [
            {
                "id": t.get("task_id", ""),
                "task_id": t.get("task_id", ""),
                "title": t.get("title") or t.get("prompt", ""),
                "prompt": t.get("prompt", ""),
                "difficulty": t.get("difficulty", "media"),
                "category": t.get("category", "geral"),
                "success_rate": {},
                "success_rate_by_executor": {},
                "runs_by_executor": {},
            }
            for t in tasks
        ]

        leaderboard = []
        for rank, (exec_name, ed) in enumerate(by_executor.items(), start=1):
            leaderboard.append(
                {
                    "rank": rank,
                    "executor": exec_name,
                    "orchestrator": exec_name.capitalize(),
                    "model": "N/A",
                    "sr": ed.get("sr"),
                    "success_rate": ed.get("success_rate"),
                    "declared": None,
                    "tua": ed.get("tool_usage_accuracy"),
                    "tool_usage_accuracy": ed.get("tool_usage_accuracy"),
                    "steps": ed.get("mean_steps"),
                    "steps_label": f"{ed.get('mean_steps', 0):.1f} passos",
                    "ctce": ed.get("ctce_usd"),
                    "ctce_usd": ed.get("ctce_usd"),
                    "composite_scores": ed.get("composite_scores"),
                }
            )

    # Caso 3: Sem dados disponíveis (inicialização limpa)
    else:
        summary_metrics = calculate_metrics_for_runs([])
        by_executor = {}
        by_difficulty = {
            level: {
                "difficulty": level,
                "run_count": 0,
                "task_count": 0,
                "verified_count": 0,
                "success_rate": None,
                "latency": {"mean_ms": None, "std_ms": None},
                "mean_latency_ms": None,
                "tool_calls": {"total": 0, "mean_steps": None},
                "mean_steps": None,
                "tua": None,
                "tool_usage_accuracy": None,
                "cost": {"mean_usd": None, "ctce_usd": None},
                "mean_cost_usd": None,
                "ctce_usd": None,
                "by_executor": {},
            }
            for level in ("baixa", "media", "alta")
        }
        paired_result = None
        profiles_payload = {
            p_name: {
                "score": 0.0,
                "weights": weights,
                "description": PROFILE_DESCRIPTIONS.get(p_name, ""),
                "by_executor": {},
            }
            for p_name, weights in DASHBOARD_PROFILES.items()
        }
        tasks_summary = [
            {
                "id": t.get("task_id", ""),
                "task_id": t.get("task_id", ""),
                "title": t.get("title") or t.get("prompt", ""),
                "prompt": t.get("prompt", ""),
                "difficulty": t.get("difficulty", "media"),
                "category": t.get("category", "geral"),
                "success_rate": {},
                "success_rate_by_executor": {},
                "runs_by_executor": {},
            }
            for t in tasks
        ]
        leaderboard = []

    return {
        "metadata": {
            "timestamp": now_iso,
            "total_runs": total_runs,
            "total_tasks": total_tasks,
            "contract_version": "0.1",
            "executors": sorted(list(by_executor.keys())),
        },
        "summary": summary_metrics,
        "by_executor": by_executor,
        "by_difficulty": by_difficulty,
        "paired_comparison": paired_result,
        "profiles": profiles_payload,
        "tasks": tasks_summary,
        "leaderboard": leaderboard,
    }


def export_dashboard(
    results_dir: Path | str = DEFAULT_RESULTS_DIR,
    output_path: Path | str = DEFAULT_OUTPUT_PATH,
    tasks_path: Path | str = DEFAULT_TASKS_PATH,
    runs: list[ExperimentRun] | None = None,
    indent: int = 2,
) -> tuple[dict[str, Any], Path]:
    """Carrega dados, monta o payload do dashboard e salva em disco como JSON."""
    r_dir = Path(results_dir)
    o_path = Path(output_path)
    t_path = Path(tasks_path)

    tasks = load_tasks_data(t_path)

    if runs is None:
        runs = load_runs_from_directory(r_dir)

    preliminary_data = None
    if not runs:
        preliminary_data = load_preliminary_report(r_dir)

    payload = build_dashboard_payload(
        runs=runs,
        tasks=tasks,
        preliminary_data=preliminary_data,
    )

    o_path.parent.mkdir(parents=True, exist_ok=True)
    o_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )
    return payload, o_path


def main(argv: list[str] | None = None) -> None:
    """CLI para exportação do payload do dashboard."""
    parser = argparse.ArgumentParser(
        description="Gera payload JSON consolidado para o Portal do Benchmark CIIA."
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Diretório de resultados contendo arquivos ExperimentRun ou relatório preliminar.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Caminho do arquivo JSON de destino (padrão: dashboard_payload.json).",
    )
    parser.add_argument(
        "--tasks-file",
        type=Path,
        default=DEFAULT_TASKS_PATH,
        help="Caminho do arquivo tasks.json (padrão: evaluation/tasks.json).",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Indentação da formatação JSON (padrão: 2).",
    )
    args = parser.parse_args(argv)

    payload, out_file = export_dashboard(
        results_dir=args.results_dir,
        output_path=args.output,
        tasks_path=args.tasks_file,
        indent=args.indent,
    )

    print(f"Payload consolidado do dashboard exportado: {out_file}")
    print(f"Total de execuções integradas: {payload['metadata']['total_runs']}")
    print(f"Total de tarefas mapeadas: {payload['metadata']['total_tasks']}")
    print(f"Executores: {', '.join(payload['metadata']['executors']) or 'Nenhum'}")


if __name__ == "__main__":
    main()

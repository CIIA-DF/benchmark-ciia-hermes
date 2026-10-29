"""Resume registros ExperimentRun sem tratar valores desconhecidos como zero."""

import argparse
import json
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
    costs = [run.cost_usd for run in runs if run.cost_usd is not None]
    tool_calls = [call for run in runs for call in run.tool_calls]
    successful_calls = sum(call.status == "ok" for call in tool_calls)

    return {
        "run_count": len(runs),
        "verified_count": len(verified),
        "success_rate": (
            sum(run.verified_success is True for run in verified) / len(verified)
            if verified
            else None
        ),
        "mean_latency_ms": sum(run.latency_ms for run in runs) / len(runs),
        "mean_cost_usd": sum(costs) / len(costs) if costs else None,
        "tool_call_count": len(tool_calls),
        "successful_tool_call_rate": (successful_calls / len(tool_calls) if tool_calls else None),
        "interpretation": ("Simulation records are pipeline checks, not agent evaluation results."),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)
    report = summarize(load_runs(args.results_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

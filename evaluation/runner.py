"""Executa tarefas de desenvolvimento em modo de simulação, sem chamar agentes."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from contracts.models import ExperimentRun

ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "evaluation" / "tasks.json"
RESULTS_PATH = ROOT / "evaluation" / "results"


def load_tasks(path: Path, split: str) -> list[dict]:
    tasks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError(f"O catálogo deve conter uma lista JSON: {path}")

    selected = []
    required = {
        "task_id",
        "split",
        "corpus_version",
        "requirements_version",
        "process_id",
        "prompt",
    }
    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not required <= task.keys():
            raise ValueError(f"Tarefa inválida na posição {index} do catálogo: {path}")
        if not all(isinstance(task[field], str) and task[field] for field in required):
            raise ValueError(f"Campos obrigatórios inválidos na tarefa {index}: {path}")
        if task["split"] == split:
            selected.append(task)

    if not selected:
        raise ValueError(f"Nenhuma tarefa encontrada para split={split!r} em {path}")
    return selected


def repository_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


def simulate(task: dict, repetition: int, commit: str, working_tree_dirty: bool) -> ExperimentRun:
    run_id = uuid4()
    return ExperimentRun(
        run_id=run_id,
        process_id=task["process_id"],
        corpus_version=task["corpus_version"],
        requirements_version=task["requirements_version"],
        task_id=task["task_id"],
        split=task["split"],
        executor="simulation",
        repetition=repetition,
        code_commit=commit,
        harness_version="0.1.0",
        adapter_version="simulation-0.1.0",
        model="not-called",
        endpoint_id="local-simulation",
        prompt_sha256=hashlib.sha256(task["prompt"].encode("utf-8")).hexdigest(),
        parameters={"simulation": True, "working_tree_dirty": working_tree_dirty},
        started_at=datetime.now(UTC),
        latency_ms=0,
        tool_calls=[],
        agent_declared_success=False,
        persisted_artifact_ids=[],
        verified_success=None,
        evaluator=None,
    )


def run_simulation(split: str, repetitions: int, results_dir: Path) -> list[Path]:
    if repetitions < 1:
        raise ValueError("O número de repetições deve ser pelo menos 1.")

    tasks = load_tasks(TASKS_PATH, split)
    commit, working_tree_dirty = repository_state()
    results_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for task in tasks:
        for repetition in range(1, repetitions + 1):
            record = simulate(task, repetition, commit, working_tree_dirty)
            path = results_dir / f"{record.run_id}.json"
            path.write_text(
                record.model_dump_json(indent=2) + "\n",
                encoding="utf-8",
            )
            paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=["simulation"], default="simulation")
    parser.add_argument("--split", choices=["development", "final"], default="development")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_PATH)
    args = parser.parse_args(argv)

    paths = run_simulation(args.split, args.repetitions, args.results_dir)
    for path in paths:
        print(f"Registro simulado (não é resultado de agente): {path}")


if __name__ == "__main__":
    main()

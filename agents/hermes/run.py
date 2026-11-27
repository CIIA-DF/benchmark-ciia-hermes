"""Executa uma ou mais tarefas de avaliação com Hermes contra a API local de ferramentas."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from agents.hermes.adapter import HermesAdapter
from contracts.models import ToolContext

ROOT = Path(__file__).resolve().parents[2]
TASKS_PATH = ROOT / "evaluation" / "tasks.json"


def _load_all_tasks() -> list[dict]:
    with TASKS_PATH.open(encoding="utf-8") as tasks_file:
        tasks = json.load(tasks_file)
    if not isinstance(tasks, list):
        raise ValueError(f"O arquivo {TASKS_PATH} deve conter uma lista de tarefas.")
    return tasks


def _validate_task(task: dict | None, task_id: str) -> dict:
    if task is None:
        raise ValueError(f"Tarefa {task_id!r} não encontrada em {TASKS_PATH}.")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        raise ValueError(f"A tarefa {task_id!r} não contém um prompt válido.")
    return task


def _load_task(task_id: str) -> dict:
    tasks = _load_all_tasks()
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("task_id") == task_id),
        None,
    )
    return _validate_task(task, task_id)


def _select_tasks(task_id: str, task_ids: str | None, run_all: bool, split: str) -> list[dict]:
    if run_all:
        tasks = [
            _validate_task(item, str(item.get("task_id", "")))
            for item in _load_all_tasks()
            if isinstance(item, dict) and item.get("split", "development") == split
        ]
        if not tasks:
            raise ValueError(f"Nenhuma tarefa encontrada para split={split!r} em {TASKS_PATH}.")
        return tasks
    if task_ids:
        ids = [item.strip() for item in task_ids.split(",") if item.strip()]
        if not ids:
            raise ValueError("--task-ids deve conter ao menos um identificador válido.")
        return [_load_task(tid) for tid in ids]
    return [_load_task(task_id)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-id",
        default="DEV-001",
        help="ID de uma tarefa de evaluation/tasks.json (padrão: DEV-001).",
    )
    parser.add_argument(
        "--task-ids",
        default=None,
        help="Lista opcional de IDs separados por vírgula (ex.: DEV-001,DEV-002).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="run_all",
        help="Executa todas as tarefas do split informado em evaluation/tasks.json.",
    )
    parser.add_argument(
        "--split",
        default="development",
        choices=["development", "final"],
        help="Split da avaliação (padrão: development).",
    )
    parser.add_argument(
        "--repetition",
        type=int,
        default=1,
        help="Número da repetição da execução (padrão: 1).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Salva o ExperimentRun em evaluation/results/{run_id}.json.",
    )
    args = parser.parse_args()

    selected_tasks = _select_tasks(args.task_id, args.task_ids, args.run_all, args.split)
    adapter = HermesAdapter()

    for task in selected_tasks:
        context = ToolContext(
            run_id=uuid4(),
            process_id=task["process_id"],
            corpus_version=task["corpus_version"],
            requirements_version=task["requirements_version"],
        )
        run = adapter.run(
            task["prompt"],
            context,
            task_id=task["task_id"],
            split=args.split,
            repetition=args.repetition,
        )

        print(f"Tarefa: {task['task_id']}")
        print("Resposta final do agente:")
        print(adapter.final_response)
        print("\nResumo da Execução:")
        print(f"  Run ID: {run.run_id}")
        print(f"  Latência: {run.latency_ms:.2f} ms")
        print(f"  Chamadas de ferramenta: {len(run.tool_calls)}")
        print(f"  Tokens: {run.input_tokens} in / {run.output_tokens} out")
        print(f"  Custo: {run.cost_usd}")

        if args.save:
            results_dir = ROOT / "evaluation" / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            result_path = results_dir / f"{run.run_id}.json"
            with result_path.open("w", encoding="utf-8") as f:
                json.dump(run.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            print(f"Resultado salvo em: {result_path}")

        print("ExperimentRun:")
        print(json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Executa uma tarefa de avaliação com Hermes contra a API local de ferramentas."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from agents.hermes.adapter import HermesAdapter
from contracts.models import ToolContext

ROOT = Path(__file__).resolve().parents[2]
TASKS_PATH = ROOT / "evaluation" / "tasks.json"


def _load_task(task_id: str) -> dict:
    with TASKS_PATH.open(encoding="utf-8") as tasks_file:
        tasks = json.load(tasks_file)
    if not isinstance(tasks, list):
        raise ValueError(f"O arquivo {TASKS_PATH} deve conter uma lista de tarefas.")

    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("task_id") == task_id),
        None,
    )
    if task is None:
        raise ValueError(f"Tarefa {task_id!r} não encontrada em {TASKS_PATH}.")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        raise ValueError(f"A tarefa {task_id!r} não contém um prompt válido.")
    return task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-id",
        default="DEV-001",
        help="ID de uma tarefa de evaluation/tasks.json (padrão: DEV-001).",
    )
    args = parser.parse_args()

    task = _load_task(args.task_id)
    context = ToolContext(
        run_id=uuid4(),
        process_id=task["process_id"],
        corpus_version=task["corpus_version"],
        requirements_version=task["requirements_version"],
    )
    adapter = HermesAdapter()
    run = adapter.run(task["prompt"], context, task_id=task["task_id"])

    print(f"Tarefa: {task['task_id']}")
    print("Resposta final do agente:")
    print(adapter.final_response)
    print("ExperimentRun:")
    print(json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

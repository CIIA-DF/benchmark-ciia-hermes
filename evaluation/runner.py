"""Executa tarefas de desenvolvimento em modo de simulação ou pareado entre adaptadores."""

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from agents.interface import AgentAdapter
from contracts.models import ExperimentRun, ToolContext

ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "evaluation" / "tasks.json"
RESULTS_PATH = ROOT / "evaluation" / "results"


def load_tasks(
    path: Path,
    split: str,
    task_ids: list[str] | None = None,
    difficulty: str | list[str] | None = None,
) -> list[dict]:
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
    diff_filter = [difficulty] if isinstance(difficulty, str) else difficulty
    if diff_filter is not None:
        diff_filter = set(diff_filter)

    for index, task in enumerate(tasks):
        if not isinstance(task, dict) or not required <= task.keys():
            raise ValueError(f"Tarefa inválida na posição {index} do catálogo: {path}")
        if not all(isinstance(task[field], str) and task[field] for field in required):
            raise ValueError(f"Campos obrigatórios inválidos na tarefa {index}: {path}")
        if task["split"] == split:
            if task_ids is not None and task["task_id"] not in task_ids:
                continue
            if diff_filter is not None and task.get("difficulty") not in diff_filter:
                continue
            selected.append(task)

    if not selected:
        raise ValueError(f"Nenhuma tarefa encontrada para split={split!r} em {path}")
    return selected


def build_tool_context(task: dict, run_id: UUID | None = None) -> ToolContext:
    """Cria ToolContext isolado com run_id exclusivo para cada execução."""
    return ToolContext(
        run_id=run_id or uuid4(),
        process_id=task["process_id"],
        corpus_version=task["corpus_version"],
        requirements_version=task["requirements_version"],
    )


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
    context = build_tool_context(task)
    return ExperimentRun(
        **context.model_dump(),
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


class SimulationAdapter:
    """Adaptador de simulação para validação determinística de harness e pipeline."""

    def __init__(
        self,
        executor_name: str = "simulation",
        commit: str | None = None,
        working_tree_dirty: bool | None = None,
        latency_ms: float = 0.0,
    ):
        self.executor_name = executor_name
        self.commit = commit
        self.working_tree_dirty = working_tree_dirty
        self.latency_ms = latency_ms

    def run(self, task: str, context: ToolContext) -> ExperimentRun:
        c = self.commit
        d = self.working_tree_dirty
        if c is None or d is None:
            c_head, d_head = repository_state()
            c = c or c_head
            d = d if d is not None else d_head

        prompt_hash = hashlib.sha256(task.encode("utf-8")).hexdigest()
        return ExperimentRun(
            **context.model_dump(),
            task_id=getattr(context, "task_id", "DEV-001"),
            split="development",
            executor="simulation",
            repetition=1,
            code_commit=c,
            harness_version="0.1.0",
            adapter_version=f"{self.executor_name}-0.1.0",
            model="not-called",
            endpoint_id=f"local-{self.executor_name}",
            prompt_sha256=prompt_hash,
            parameters={"simulation": True, "working_tree_dirty": d},
            started_at=datetime.now(UTC),
            latency_ms=self.latency_ms,
            tool_calls=[],
            agent_declared_success=False,
            persisted_artifact_ids=[],
            verified_success=None,
            evaluator=None,
        )


def resolve_adapter(name: str) -> AgentAdapter:
    """Retorna adaptador registrado ou levanta NotImplementedError quando pendente."""
    if name == "simulation":
        return SimulationAdapter()
    if name == "hermes":
        try:
            from agents.hermes.adapter import HermesAdapter  # type: ignore

            return HermesAdapter()
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            raise NotImplementedError(
                "Adaptador 'hermes' ainda não está implementado/instalado nesta branch "
                "(identidade, versão e endpoint pendentes conforme agents/hermes/README.md). "
                "Conforme regras (AGENTS.md), não inventamos dependências ou resultados."
            ) from exc
    if name == "langgraph":
        try:
            from agents.langgraph.adapter import LangGraphAdapter  # type: ignore

            return LangGraphAdapter()
        except (ImportError, ModuleNotFoundError, AttributeError) as exc:
            raise NotImplementedError(
                "Adaptador 'langgraph' ainda não está implementado/instalado nesta branch "
                "(conforme agents/langgraph/README.md). Conforme regras operacionais (AGENTS.md), "
                "não inventamos dependências ou resultados."
            ) from exc
    raise ValueError(f"Adaptador desconhecido: {name!r}")


def run_simulation(
    split: str,
    repetitions: int,
    results_dir: Path,
    task_ids: list[str] | None = None,
    difficulty: str | list[str] | None = None,
) -> list[Path]:
    if repetitions < 1:
        raise ValueError("O número de repetições deve ser pelo menos 1.")

    tasks = load_tasks(TASKS_PATH, split, task_ids=task_ids, difficulty=difficulty)
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


def run_paired_adapters(
    tasks: list[dict],
    adapters: dict[str, AgentAdapter],
    repetitions: int,
    results_dir: Path,
) -> list[Path]:
    """Executa adaptadores em pareamento contrabalanceado (ordem alternada por repetição)."""
    if repetitions < 1:
        raise ValueError("O número de repetições deve ser pelo menos 1.")
    if len(adapters) < 2:
        raise ValueError("Execução pareada exige pelo menos dois adaptadores.")

    names = list(adapters.keys())
    results_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for task in tasks:
        for repetition in range(1, repetitions + 1):
            ordered_names = names if repetition % 2 == 1 else list(reversed(names))
            for name in ordered_names:
                context = build_tool_context(task)
                record = adapters[name].run(task["prompt"], context)
                path = results_dir / f"{record.run_id}.json"
                path.write_text(
                    record.model_dump_json(indent=2) + "\n",
                    encoding="utf-8",
                )
                paths.append(path)
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--adapter",
        choices=["simulation", "hermes", "langgraph", "paired"],
        default="simulation",
        help="Executor alvo ou 'paired' para execução pareada",
    )
    parser.add_argument(
        "--split",
        choices=["development", "final"],
        default="development",
        help="Subconjunto de tarefas no catálogo",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=None,
        help="Número de repetições por tarefa",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="Sinônimo de --repetitions",
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        default=None,
        help="Lista opcional de tarefas separadas por vírgula (ex: DEV-001,DEV-002)",
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        default=None,
        help="Filtrar por nível de dificuldade separado por vírgula (ex: baixa,media,alta)",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=RESULTS_PATH,
        help="Diretório onde salvar os registros JSON de ExperimentRun",
    )
    args = parser.parse_args(argv)

    repetitions = args.repeats if args.repeats is not None else (args.repetitions or 1)
    if repetitions < 1:
        parser.error("O número de repetições deve ser pelo menos 1.")

    task_id_list = (
        [t.strip() for t in args.task_ids.split(",") if t.strip()] if args.task_ids else None
    )
    difficulty_list = (
        [d.strip() for d in args.difficulty.split(",") if d.strip()] if args.difficulty else None
    )
    tasks = load_tasks(
        TASKS_PATH,
        args.split,
        task_ids=task_id_list,
        difficulty=difficulty_list,
    )

    if args.adapter == "simulation":
        paths = run_simulation(
            args.split,
            repetitions=repetitions,
            results_dir=args.results_dir,
            task_ids=task_id_list,
            difficulty=difficulty_list,
        )
        for path in paths:
            print(f"Registro simulado (não é resultado de agente): {path}")
        print(f"Sucesso: {len(paths)} execuções salvas em {args.results_dir}")
    elif args.adapter in ("hermes", "langgraph"):
        try:
            adapter = resolve_adapter(args.adapter)
        except NotImplementedError as exc:
            print(f"AVISO: {exc}")
            print("Para testar o pipeline e a coleta, use '--adapter simulation'.")
            return
        paths: list[Path] = []
        for task in tasks:
            for _repetition in range(1, repetitions + 1):
                context = build_tool_context(task)
                record = adapter.run(task["prompt"], context)
                path = args.results_dir / f"{record.run_id}.json"
                path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
                paths.append(path)
        print(f"Sucesso: {len(paths)} execuções de {args.adapter} salvas em {args.results_dir}")
    elif args.adapter == "paired":
        try:
            adapters = {
                "hermes": resolve_adapter("hermes"),
                "langgraph": resolve_adapter("langgraph"),
            }
        except NotImplementedError as exc:
            print(f"BLOQUEIO NA EXECUÇÃO PAREADA: {exc}")
            print(
                "Ambos os adaptadores reais precisam estar implementados para a rodada pareada. "
                "Conforme protocolo (AGENTS.md), não inventamos resultados de agentes."
            )
            return
        paths = run_paired_adapters(tasks, adapters, repetitions, args.results_dir)
        print(f"Sucesso: {len(paths)} execuções pareadas salvas em {args.results_dir}")


if __name__ == "__main__":
    main()

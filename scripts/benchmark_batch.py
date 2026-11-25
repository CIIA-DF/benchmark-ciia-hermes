"""Cria runs de benchmark em lote: tarefa × executor × repetição, por POST /runs.

Lê tarefas no formato de ``evaluation/tasks.json`` (task_id, split, process_id, corpus_version,
requirements_version, prompt). Só o ``prompt`` vai para o agente; gabarito e critérios de
aceite ficam fora do run. A chave de idempotência é ``rotulo:tarefa:executor:repeticao``:
repetir o comando com o mesmo rótulo devolve os mesmos runs, sem duplicar.

Ordem intercalada e contrabalançada (``evaluation/protocol.md``): repetição -> tarefa ->
executor, com a ordem dos executores girando a cada tarefa e repetição, para que Hermes e
LangGraph rodem sob as mesmas condições de horário e carga e cada um vá primeiro na mesma
proporção. A ordem é determinística e ``position`` registra a ordem de envio.

Mantém no máximo ``--window`` runs não terminais, porque a fila tem cota por operador e runs
parados além de RUN_QUEUE_TIMEOUT_SECONDS expiram. Falhas passageiras (erro de transporte ou 5xx
``retryable``) são repetidas com espera crescente; o lote só desiste quando nada avança por
``--stall-seconds``. Escreve um manifesto JSON Lines com o run_id de cada combinação e, se parar,
uma linha ``not_submitted`` para cada item não enviado. Não avalia respostas.
"""

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable

import httpx

from contracts.execution import TERMINAL_STATUSES

# Sem ":" no rótulo, na tarefa e no executor: ":" só separa as partes da chave de idempotência,
# senão "a:b" + "c" e "a" + "b:c" gerariam a mesma chave e reaproveitariam o run errado.
IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
TERMINAL = TERMINAL_STATUSES
SCOPE = ("process_id", "corpus_version", "requirements_version")
# Sem progresso por esse tempo, o lote desiste: o dobro de RUN_QUEUE_TIMEOUT_SECONDS +
# RUN_TIMEOUT_SECONDS (300 s cada), prazo em que um run aceito já deveria ter terminado.
STALL_SECONDS = 1200.0
RETRY_CAP_SECONDS = 30.0
MANIFEST_FIELDS = ("idempotency_key", "task_id", "executor", "repetition")


def plan(tasks: list[dict], executors: list[str], repetitions: int, label: str) -> list[dict]:
    if not IDENTIFIER.match(label):
        raise ValueError("Rótulo deve usar letras, dígitos e . _ - (até 120), sem ':'.")
    if repetitions < 1 or not executors:
        raise ValueError("Informe ao menos um executor e uma repetição.")
    for executor in executors:
        if not IDENTIFIER.match(executor):
            raise ValueError(f"Executor inválido para a chave: {executor}")
    seen = set()
    for task in tasks:
        if not IDENTIFIER.match(str(task["task_id"])):
            raise ValueError(
                f"task_id deve usar letras, dígitos e . _ -, sem ':': {task['task_id']}"
            )
        if task["task_id"] in seen:
            raise ValueError(f"task_id repetido: {task['task_id']}")
        seen.add(task["task_id"])
    items = []
    for repetition in range(1, repetitions + 1):
        for index, task in enumerate(tasks):
            # Contrabalanço: a ordem dos executores gira a cada tarefa e repetição, e cada um
            # vai primeiro na mesma proporção dos pares (protocolo da Metodologia).
            shift = (repetition - 1 + index) % len(executors)
            for executor in executors[shift:] + executors[:shift]:
                key = f"{label}:{task['task_id']}:{executor}:{repetition}"
                if len(key) > 120:
                    raise ValueError(f"Chave de idempotência longa demais: {key}")
                items.append(
                    {
                        **{k: task[k] for k in SCOPE},
                        "executor": executor,
                        "task": task["prompt"],
                        "task_id": task["task_id"],
                        "split": task.get("split", "development"),
                        "repetition": repetition,
                        "idempotency_key": key,
                    }
                )
    return items


def _retryable(response: httpx.Response) -> bool:
    # Só 5xx que o backend declara passageiros (ex.: 503 storage_unavailable); o resto encerra.
    if response.status_code < 500:
        return False
    try:
        return response.json().get("retryable") is True
    except ValueError:
        return False


def submit(
    http: httpx.Client,
    items: list[dict],
    *,
    window: int = 4,
    poll_seconds: float = 5.0,
    stall_seconds: float = STALL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    emit: Callable[[dict], None] = lambda row: None,
) -> list[dict]:
    """Envia os runs respeitando a janela; devolve uma linha de manifesto por run.

    O prazo é de progresso, não do lote inteiro: renova a cada run aceito ou terminado.
    """
    if window < 1:
        raise ValueError("window deve ser positivo.")
    active: set[str] = set()
    manifest = []
    last_progress = clock()

    def progressed():
        nonlocal last_progress
        last_progress = clock()

    def check_stall():
        if clock() - last_progress > stall_seconds:
            raise TimeoutError(f"Lote sem progresso por mais de {stall_seconds:.0f} s.")

    def request(method: str, path: str, **kwargs) -> httpx.Response:
        delay = 1.0
        while True:
            try:
                response = getattr(http, method)(path, **kwargs)
            except httpx.TransportError:
                response = None
            if response is not None and not _retryable(response):
                return response
            check_stall()
            sleep(min(delay, RETRY_CAP_SECONDS))
            delay *= 2

    def refresh():
        for run_id in list(active):
            response = request("get", f"/runs/{run_id}")
            response.raise_for_status()
            if response.json()["status"] in TERMINAL:
                active.discard(run_id)
                progressed()

    def wait():
        check_stall()
        sleep(poll_seconds)
        refresh()

    try:
        for position, item in enumerate(items, start=1):
            while len(active) >= window:
                wait()
            while True:
                # Repetir o POST é seguro: a idempotency_key devolve o mesmo run se a resposta
                # anterior se perdeu no caminho.
                response = request("post", "/runs", json=item)
                if response.status_code == 429 and response.json().get("code") == "resource_limit":
                    wait()
                    continue
                response.raise_for_status()
                break
            progressed()
            run = response.json()
            row = {
                **{k: item[k] for k in MANIFEST_FIELDS},
                "position": position,
                "run_id": run["run_id"],
                "status": run["status"],
            }
            if run["status"] not in TERMINAL:
                active.add(run["run_id"])
            manifest.append(row)
            emit(row)
    except BaseException:
        # O protocolo pede relatar todas as execuções previstas: o manifesto parcial lista os
        # itens não enviados. Retomar com o mesmo rótulo reaproveita os runs já criados.
        for index in range(len(manifest) + 1, len(items) + 1):
            emit(
                {
                    **{k: items[index - 1][k] for k in MANIFEST_FIELDS},
                    "position": index,
                    "run_id": None,
                    "status": "not_submitted",
                }
            )
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", help="Arquivo JSON no formato de evaluation/tasks.json")
    parser.add_argument("--label", required=True, help="Rótulo da rodada; fixa a idempotência")
    parser.add_argument("--executor", action="append", required=True, dest="executors")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--split", choices=["development", "final"])
    parser.add_argument("--window", type=int, default=4)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument(
        "--stall-seconds",
        type=float,
        default=STALL_SECONDS,
        help="Desiste só se nenhum run for aceito ou terminar nesse intervalo",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o plano")
    args = parser.parse_args()
    with open(args.tasks, encoding="utf-8") as stream:
        tasks = json.load(stream)
    if args.split:
        tasks = [t for t in tasks if t.get("split", "development") == args.split]
    try:
        items = plan(tasks, args.executors, args.repetitions, args.label)
    except (KeyError, ValueError) as exc:
        parser.error(str(exc))
    if args.dry_run:
        for position, item in enumerate(items, start=1):
            shown = {k: v for k, v in item.items() if k != "task"}
            print(json.dumps({**shown, "position": position}, ensure_ascii=False))
        return
    token = os.environ.get("BACKEND_OPERATOR_TOKEN")
    if not token:
        parser.error("Defina BACKEND_OPERATOR_TOKEN no ambiente privado.")
    with httpx.Client(
        base_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    ) as http:
        submit(
            http,
            items,
            window=args.window,
            poll_seconds=args.poll_seconds,
            stall_seconds=args.stall_seconds,
            emit=lambda row: print(json.dumps(row, ensure_ascii=False), flush=True),
        )
    print(f"runs={len(items)}", file=sys.stderr)


if __name__ == "__main__":
    main()

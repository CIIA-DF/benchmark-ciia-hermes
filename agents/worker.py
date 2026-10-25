"""Worker HTTP comum. Adapters reais são registrados pelas equipes, sem acesso ao banco."""

import argparse
import asyncio
import os

import httpx

from agents.interface import AsyncToolClient
from agents.registry import load_adapter
from contracts.execution import AgentEvent, AgentResult, ClaimedRun


async def post(client, path, value, headers=None):
    # Somente operações idempotentes usam retry com a mesma entrada/event_id.
    for attempt in range(3):
        try:
            response = await client.post(path, json=value, headers=headers)
            if response.status_code >= 500 and attempt < 2:
                await asyncio.sleep(0.3 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        except httpx.TransportError:
            if attempt == 2:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))


async def execute(client, execution, adapter):
    headers = {"X-Run-Token": execution.run_token}
    base = f"/runs/{execution.run_id}"
    stopped = asyncio.Event()
    # Heartbeat e resultado final não se cruzam: depois do resultado a reserva já terminou.
    finishing = asyncio.Lock()

    async def heartbeat():
        while not stopped.is_set():
            try:
                await asyncio.wait_for(stopped.wait(), timeout=execution.heartbeat_seconds)
            except TimeoutError:
                async with finishing:
                    if not stopped.is_set():
                        await post(client, base + "/heartbeat", {}, headers)

    async def finish(result):
        async with finishing:
            try:
                await post(client, base + "/result", result.model_dump(mode="json"), headers)
            finally:
                stopped.set()

    async def consume():
        try:
            finished = False
            async for item in adapter.stream(execution, AsyncToolClient(client, execution)):
                if finished:
                    raise ValueError("Adaptador enviou dados após o resultado final.")
                if isinstance(item, AgentEvent):
                    await post(client, base + "/events", item.model_dump(mode="json"), headers)
                elif isinstance(item, AgentResult):
                    await finish(item)
                    finished = True
                else:
                    raise ValueError("Evento fora do contrato.")
            if not finished:
                raise ValueError("Adaptador encerrou sem resultado.")
        except Exception:
            await finish(AgentResult(status="failed", error_code="adapter_error"))
            raise
        finally:
            stopped.set()

    async with asyncio.TaskGroup() as group:
        group.create_task(consume())
        group.create_task(heartbeat())


async def work(adapter, executor, *, once=False):
    token = os.environ["BACKEND_WORKER_TOKEN"]
    async with httpx.AsyncClient(
        base_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    ) as client:
        while True:
            # Cada polling é uma nova reserva; uma resposta perdida expira pela lease.
            try:
                response = await client.post("/runs/claim", json={"executor": executor})
            except httpx.TransportError:
                if once:
                    raise
                print("status=backend_unavailable", flush=True)
                await asyncio.sleep(2)
                continue
            if response.status_code == 503 and not once:
                print("status=backend_unavailable", flush=True)
                await asyncio.sleep(2)
                continue
            response.raise_for_status()
            if response.status_code != 204:
                execution = ClaimedRun.model_validate(response.json())
                try:
                    await execute(client, execution, adapter)
                except ExceptionGroup:
                    print(f"run_id={execution.run_id} status=worker_error", flush=True)
            if once:
                return
            await asyncio.sleep(0.4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--executor", choices=["simulation", "hermes", "langgraph"], default="simulation"
    )
    parser.add_argument("--adapter", help="Fábrica local modulo:funcao entregue pela equipe")
    args = parser.parse_args()
    try:
        adapter = load_adapter(args.executor, args.adapter)
    except ValueError as exc:
        parser.error(str(exc))
    asyncio.run(work(adapter, args.executor, once=args.once))


if __name__ == "__main__":
    main()

"""Medições sintéticas do item 9 da auditoria de 30/10 (P9), com SQLite temporário.

Não usa banco operacional, rede ou LLM. Mede custo relativo antes e depois de uma mudança; os
números dependem da máquina e não valem como desempenho de produção.

    uv run --locked python -m scripts.measure_backend events --count 2500
"""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from pipelines.documents.ingest import chunk_document, load_fixture
from scripts.checklist import import_checklist
from scripts.demo import ROOT
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.storage import ingest, initialize, make_engine


def environment(directory: Path):
    engine = make_engine(f"sqlite:///{directory / 'measure.db'}")
    initialize(engine)
    process, document = load_fixture(ROOT / "examples")
    ingest(engine, process, document, chunk_document(document))
    import_checklist(
        engine,
        process.process_id,
        process.corpus_version,
        process.requirements_version,
        [{"requirement_id": "REQ-1", "description": "Fictício", "source": "Medição"}],
    )
    operator, worker = uuid4().hex, uuid4().hex
    grants = [(process.process_id, process.corpus_version)]
    provision(engine, "measure-operator", operator, "operator", grants, can_write=True)
    provision(
        engine, "measure-worker", worker, "worker", grants, can_write=True, executor="simulation"
    )
    scope = {
        "process_id": process.process_id,
        "corpus_version": process.corpus_version,
        "requirements_version": process.requirements_version,
    }
    return (
        engine,
        scope,
        {"Authorization": f"Bearer {operator}"},
        {"Authorization": f"Bearer {worker}"},
    )


def events(count: int, chars: int) -> dict:
    """Custo de POST /runs/{id}/events por faixa de deltas já gravados."""
    with tempfile.TemporaryDirectory() as tmp:
        engine, scope, operator, worker = environment(Path(tmp))
        with TestClient(create_app(engine)) as client:
            created = client.post(
                "/runs",
                headers=operator,
                json={**scope, "task": "Medição", "task_id": "M-1", "idempotency_key": "m"},
            )
            created.raise_for_status()
            claim = client.post("/runs/claim", headers=worker, json={"executor": "simulation"})
            claim.raise_for_status()
            run = claim.json()
            headers = {**worker, "X-Run-Token": run["run_token"]}
            path = f"/runs/{run['run_id']}/events"
            heartbeat = f"/runs/{run['run_id']}/heartbeat"
            window = max(1, count // 10)
            timings, durations = [], []
            for index in range(count):
                if index % 20 == 0:
                    # Fora do tempo medido: mantém a reserva ativa durante a medição.
                    client.post(heartbeat, headers=headers).raise_for_status()
                started = time.perf_counter()
                response = client.post(
                    path,
                    headers=headers,
                    json={"event_id": str(uuid4()), "kind": "text_delta", "text": "x" * chars},
                )
                durations.append(time.perf_counter() - started)
                response.raise_for_status()
                if index % window == window - 1:
                    # Mediana da faixa: picos isolados da máquina não dominam o resultado.
                    timings.append(round(statistics.median(durations) * 1000, 3))
                    durations = []
        engine.dispose()
    return {
        "measure": "events",
        "count": count,
        "chars": chars,
        "median_ms_per_event_by_decile": timings,
        "last_over_first": round(timings[-1] / timings[0], 2) if timings else None,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="measure", required=True)
    ev = sub.add_parser("events", help="custo por evento text_delta ao longo do run")
    ev.add_argument("--count", type=int, default=2500)
    ev.add_argument("--chars", type=int, default=40)
    args = parser.parse_args(argv)
    if args.count * args.chars > 100_000:
        parser.error("count × chars não pode passar do limite de 100.000 caracteres.")
    print(json.dumps(events(args.count, args.chars)))


if __name__ == "__main__":
    main()

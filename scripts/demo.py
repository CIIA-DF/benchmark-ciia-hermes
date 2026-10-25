"""Demonstração verificável, local ou via API HTTP; somente corpus fictício."""

import argparse
import json
import os
import secrets
import time
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from contracts.models import ProcessResult, SearchResult
from pipelines.documents.ingest import chunk_document, load_fixture
from scripts.checklist import import_checklist
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.storage import ingest, initialize, make_engine

ROOT = Path(__file__).resolve().parents[1]


def seed() -> int:
    engine = make_engine()
    initialize(engine)
    process, document = load_fixture(ROOT / "examples")
    try:
        count = ingest(engine, process, document, chunk_document(document))
        import_checklist(
            engine,
            process.process_id,
            process.corpus_version,
            process.requirements_version,
            json.loads((ROOT / "examples/requirements.json").read_text(encoding="utf-8")),
        )
        return count
    finally:
        engine.dispose()


def verify(client, operator_token, worker_token) -> dict:
    scope = {
        "process_id": "PROC-DEMO-001",
        "corpus_version": "synthetic-v1",
        "requirements_version": "demo-v1",
    }
    response = client.post(
        "/runs",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            **scope,
            "task": "Conferência da base fictícia",
            "task_id": "DEV-DEMO",
            "idempotency_key": str(uuid4()),
        },
    )
    response.raise_for_status()
    created_run_id = response.json()["run_id"]
    response = client.post(
        "/runs/claim",
        headers={"Authorization": f"Bearer {worker_token}"},
        json={"executor": "simulation", "run_id": created_run_id},
    )
    response.raise_for_status()
    if response.status_code == 204:
        # Um worker já ativo pode ter reservado a verificação; nunca assumir outra tarefa.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = client.get(
                f"/runs/{created_run_id}", headers={"Authorization": f"Bearer {operator_token}"}
            )
            state.raise_for_status()
            if state.json()["status"] == "succeeded":
                return {"verification_run": state.json()}
            if state.json()["status"] in {"failed", "timed_out"}:
                raise RuntimeError("Worker não concluiu a verificação da demo.")
            time.sleep(0.2)
        raise RuntimeError("A verificação continua em execução; consulte o run_id no portal.")
    claim = response.json()
    context = claim["context"]
    headers = {"Authorization": f"Bearer {worker_token}", "X-Run-Token": claim["run_token"]}
    response = client.post("/tools/consultar_processo", json=context, headers=headers)
    response.raise_for_status()
    process = ProcessResult.model_validate(response.json())
    response = client.post(
        "/tools/buscar_documentos", json={**context, "query": "material"}, headers=headers
    )
    response.raise_for_status()
    results = SearchResult.model_validate(response.json())
    if not results.items or any(item.process_id != context["process_id"] for item in results.items):
        raise RuntimeError("A busca não retornou evidências válidas para o processo.")
    response = client.post(
        f"/runs/{context['run_id']}/result",
        headers=headers,
        json={"status": "failed", "error_code": "adapter_error"},
    )
    response.raise_for_status()
    return {"process": process.model_dump(mode="json"), "search": results.model_dump(mode="json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Consulta API HTTP já populada; não ingere remotamente.")
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args()
    if args.url and args.seed_only:
        parser.error("Use --url ou --seed-only, separadamente.")
    if not args.url:
        print(f"Chunks novos persistidos: {seed()}")
    if args.seed_only:
        return
    if args.url:
        with httpx.Client(base_url=args.url, timeout=15) as client:
            result = verify(
                client, os.environ["BACKEND_OPERATOR_TOKEN"], os.environ["BACKEND_WORKER_TOKEN"]
            )
    else:
        operator_token, worker_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        database = make_engine()
        grants = [("PROC-DEMO-001", "synthetic-v1")]
        suffix = uuid4().hex
        provision(database, "demo-operator-" + suffix, operator_token, "operator", grants)
        provision(
            database, "demo-worker-" + suffix, worker_token, "worker", grants, executor="simulation"
        )
        database.dispose()
        # Outra engine/conexão comprova leitura após commit, usando a API ASGI real.
        with TestClient(create_app()) as client:
            result = verify(client, operator_token, worker_token)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

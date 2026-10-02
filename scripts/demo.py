"""Demonstração verificável, local ou via API HTTP; somente corpus fictício."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from contracts.models import ProcessResult, SearchResult
from pipelines.documents.ingest import chunk_document, load_fixture
from services.backend.app import create_app
from services.backend.storage import ingest, initialize, make_engine

ROOT = Path(__file__).resolve().parents[1]


def seed() -> int:
    engine = make_engine()
    initialize(engine)
    process, document = load_fixture(ROOT / "examples")
    try:
        return ingest(engine, process, document, chunk_document(document))
    finally:
        engine.dispose()


def verify(client) -> dict:
    context = {
        "run_id": str(uuid4()),
        "process_id": "PROC-DEMO-001",
        "corpus_version": "synthetic-v1",
        "requirements_version": "demo-v1",
    }
    response = client.post("/tools/consultar_processo", json=context)
    response.raise_for_status()
    process = ProcessResult.model_validate(response.json())
    response = client.post("/tools/buscar_documentos", json={**context, "query": "material"})
    response.raise_for_status()
    results = SearchResult.model_validate(response.json())
    if not results.items or any(item.process_id != context["process_id"] for item in results.items):
        raise RuntimeError("A busca não retornou evidências válidas para o processo.")
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
            result = verify(client)
    else:
        # Outra engine/conexão comprova leitura após commit, usando a API ASGI real.
        with TestClient(create_app()) as client:
            result = verify(client)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

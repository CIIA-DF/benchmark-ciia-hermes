"""Demonstra as seis tools com dados fictícios, sem agente ou LLM."""

import hashlib
import json
import secrets
from uuid import uuid4

from fastapi.testclient import TestClient

from scripts.demo import seed
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.storage import make_engine


def demonstrate():
    seed()
    database = make_engine()
    operator, worker = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    scope = {
        "process_id": "PROC-DEMO-001",
        "corpus_version": "synthetic-v1",
        "requirements_version": "demo-v1",
    }
    grants = [(scope["process_id"], scope["corpus_version"])]
    suffix = uuid4().hex
    provision(database, "tools-operator-" + suffix, operator, "operator", grants, can_write=True)
    provision(
        database,
        "tools-worker-" + suffix,
        worker,
        "worker",
        grants,
        can_write=True,
        executor="simulation",
    )
    operator_headers = {"Authorization": "Bearer " + operator}
    with TestClient(create_app(database)) as client:

        def post(path, value, headers):
            response = client.post(path, json=value, headers=headers)
            response.raise_for_status()
            return response.json()

        conversation = post("/conversations", scope, operator_headers)
        run = post(
            f"/conversations/{conversation['conversation_id']}/messages",
            {
                "content": "Demonstração sintética das seis ferramentas.",
                "idempotency_key": str(uuid4()),
            },
            operator_headers,
        )
        claim = post(
            "/runs/claim",
            {"executor": "simulation", "run_id": run["run_id"]},
            {"Authorization": "Bearer " + worker},
        )
        headers = {"Authorization": "Bearer " + worker, "X-Run-Token": claim["run_token"]}

        def tool(name, **arguments):
            return post(f"/tools/{name}", {**arguments, **claim["context"]}, headers)

        tool("consultar_processo")
        found = tool("buscar_documentos", query="material")
        source = found["items"][0]
        tool("ler_documento", document_id=source["document_id"], pages=[source["page"]])
        checklist = tool("consultar_requisitos")
        payload = {
            "idempotency_key": "demo-1",
            "content": "Conteúdo fictício da demonstração de tools.",
            "evidence_note": "Fixture sintética: não é análise normativa.",
            "evidence": [{key: source[key] for key in ("document_id", "chunk_id", "page")}],
        }
        receipts = []
        for name in ("registrar_pendencia", "salvar_minuta"):
            value = dict(payload)
            if name == "registrar_pendencia":
                value["requirement_id"] = checklist["items"][0]["requirement_id"]
            receipt = tool(name, **value)
            replay = tool(name, **value)
            if not replay["replayed"] or replay["artifact_id"] != receipt["artifact_id"]:
                raise RuntimeError("Replay não confirmou a operação original.")
            saved = client.get(f"/artifacts/{receipt['artifact_id']}", headers=operator_headers)
            saved.raise_for_status()
            content = saved.json()["payload"]["content"]
            if (
                content != value["content"]
                or hashlib.sha256(content.encode()).hexdigest() != (receipt["content_sha256"])
            ):
                raise RuntimeError("Leitura independente não confirmou o conteúdo.")
            receipts.append(
                {
                    "tool": name,
                    "artifact_id": receipt["artifact_id"],
                    "hash_verified": True,
                    "replay_verified": True,
                }
            )
        post(
            f"/runs/{run['run_id']}/result",
            {
                "status": "succeeded",
                "answer": "Demonstração técnica concluída; nenhuma LLM chamada.",
            },
            headers,
        )
    return {
        "run_id": run["run_id"],
        "tools_verified": 6,
        "artifacts": receipts,
        "real_agent": False,
    }


if __name__ == "__main__":
    print(json.dumps(demonstrate(), ensure_ascii=False, indent=2))

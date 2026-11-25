"""Reproduce backend audit findings using only a temporary synthetic SQLite database.

This is a diagnostic, not a security acceptance test. No server or real agent is used.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from contracts.models import ExperimentRun
from pipelines.documents.ingest import chunk_document, load_fixture
from services.backend.app import create_app
from services.backend.auth import bootstrap, provision
from services.backend.schema import permissions, principals
from services.backend.storage import ingest, initialize, make_engine


def probe() -> dict[str, object]:
    with TemporaryDirectory(prefix="ciia-audit-") as folder:
        engine = make_engine(f"sqlite:///{Path(folder) / 'synthetic.db'}")
        initialize(engine)
        process, document = load_fixture(Path(__file__).resolve().parents[1] / "examples")
        ingest(engine, process, document, chunk_document(document))
        grants = [(process.process_id, process.corpus_version)]
        provision(engine, "audit-operator", "o" * 32, "operator", grants, can_write=True)
        provision(
            engine,
            "audit-worker",
            "w" * 32,
            "worker",
            grants,
            can_write=True,
            executor="simulation",
        )
        app = create_app(engine)
        with TestClient(app) as client:
            operator = {"Authorization": "Bearer " + "o" * 32}
            worker = {"Authorization": "Bearer " + "w" * 32}
            scope = {
                key: getattr(process, key)
                for key in ("process_id", "corpus_version", "requirements_version")
            }
            denied = client.get("/processos")
            observations = {
                "missing_auth_http": denied.status_code,
                "www_authenticate": denied.headers.get("www-authenticate"),
            }
            queued = client.post(
                "/runs",
                headers=operator,
                json={
                    **scope,
                    "task": "Synthetic audit",
                    "task_id": "AUDIT",
                    "idempotency_key": str(uuid4()),
                },
            )
            queued.raise_for_status()
            claimed = client.post(
                "/runs/claim",
                headers=worker,
                json={"executor": "simulation", "run_id": queued.json()["run_id"]},
            )
            claimed.raise_for_status()
            claim = claimed.json()
            headers = {
                **worker,
                "X-Run-Token": claim["run_token"],
                "X-Tool-Call-Id": "same-logical-id",
            }
            app.state.execution.max_tool_calls = 1
            receipts = []
            for index in range(2):
                response = client.post(
                    "/tools/salvar_minuta",
                    headers=headers,
                    json={
                        **claim["context"],
                        "idempotency_key": f"draft-{index}",
                        "content": f"Synthetic draft {index}",
                        "evidence": [
                            {
                                "kind": "inventory",
                                "process_id": process.process_id,
                                "corpus_version": process.corpus_version,
                            }
                        ],
                        "evidence_note": "Synthetic inventory limitation",
                    },
                )
                receipts.append((response.status_code, response.json().get("artifact_id")))
            observations["budget_one_two_different_writes"] = {
                "statuses": [item[0] for item in receipts],
                "distinct_artifacts": len({item[1] for item in receipts if item[1]}),
            }
            report = ExperimentRun(
                **claim["context"],
                task_id="AUDIT",
                split="development",
                executor="simulation",
                repetition=1,
                code_commit="synthetic",
                harness_version="audit",
                adapter_version="audit",
                model="not-called",
                endpoint_id="none",
                prompt_sha256="0" * 64,
                parameters={},
                started_at=datetime.now(UTC),
                latency_ms=0,
                tool_calls=[
                    {
                        "tool_call_id": "never-recorded",
                        "tool": "salvar_minuta",
                        "duration_ms": 0,
                        "status": "ok",
                        "artifact_id": "invented-artifact",
                    }
                ],
                agent_declared_success=True,
                persisted_artifact_ids=[],
                verified_success=None,
                evaluator=None,
            )
            finished = client.post(
                f"/runs/{claim['run_id']}/result",
                headers=headers,
                json={
                    "status": "succeeded",
                    "answer": "Synthetic answer",
                    "experiment": report.model_dump(mode="json"),
                },
            )
            observations["unverified_tool_record_result_http"] = finished.status_code
            snapshot = client.get(f"/runs/{claim['run_id']}", headers=operator)
            observations["run_cache_control"] = snapshot.headers.get("cache-control")
            app.state.execution.enabled.add("hermes")
            capabilities = client.get("/capabilities", headers=operator).json()
            observations["configured_hermes_without_worker"] = next(
                item["available"] for item in capabilities["executors"] if item["name"] == "hermes"
            )
            observations["health"] = client.get("/health").json()
            provision(engine, "local-operator", "b" * 32, "operator", [], can_write=False)
            with patch.dict(os.environ, {"BACKEND_OPERATOR_TOKEN": "b" * 32}):
                bootstrap(engine)
            with engine.connect() as connection:
                writable = connection.execute(
                    select(principals.c.can_write).where(
                        principals.c.principal_id == "local-operator"
                    )
                ).scalar_one()
                restored = (
                    connection.execute(
                        select(permissions).where(permissions.c.principal_id == "local-operator")
                    ).first()
                    is not None
                )
            observations["bootstrap_restores_local_write_and_grant"] = bool(writable and restored)
        return observations


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

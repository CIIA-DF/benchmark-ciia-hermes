"""Integrated regressions: business failures must retain logical identity/budget."""

import pytest
from sqlalchemy import delete, func, select, update

from pipelines.documents.ingest import chunk_document
from services.backend.corpus import CorpusRepository
from services.backend.schema import artifacts, logical_tool_calls, permissions, runs
from services.backend.storage import chunks, documents, ingest, processes
from tests.backend.test_tool_calls import history, write_body


@pytest.mark.parametrize(("failure", "status"), [("version_mismatch", 409), ("not_found", 404)])
def test_business_failure_keeps_identity_budget_and_can_retry_after_repair(
    client, context, engine, corpus, failure, status, monkeypatch
):
    process, document = corpus
    service = client.app.state.execution
    service.max_tool_calls = 1
    with engine.begin() as conn:
        if failure == "version_mismatch":
            payload = process.model_dump(mode="json") | {"requirements_version": "OTHER"}
            conn.execute(
                update(processes)
                .where(
                    processes.c.process_id == process.process_id,
                    processes.c.corpus_version == process.corpus_version,
                )
                .values(payload=payload)
            )
        else:
            for table in (chunks, documents, processes):
                conn.execute(
                    delete(table).where(
                        table.c.process_id == process.process_id,
                        table.c.corpus_version == process.corpus_version,
                    )
                )
    original = CorpusRepository.process

    def observed_domain(self, conn, scope):
        # A different connection must see the binding before any domain access:
        # an insert in the effect transaction without a prior commit is insufficient.
        with engine.connect() as observer:
            assert (
                observer.execute(
                    select(func.count())
                    .select_from(logical_tool_calls)
                    .where(logical_tool_calls.c.run_id == context["run_id"])
                ).scalar_one()
                == 1
            )
        return original(self, conn, scope)

    monkeypatch.setattr(CorpusRepository, "process", observed_domain)
    headers = {"X-Tool-Call-Id": "business-failed"}
    result = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert result.status_code == status and result.json()["code"] == failure
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()
        )
    assert row["tool"] == "consultar_processo"
    assert row["tool_call_id"] == headers["X-Tool-Call-Id"]
    recorded = history(client, engine, context["run_id"])
    assert len(recorded) == 1 and recorded[0]["http_status"] == status
    assert recorded[0]["code"] == failure
    assert row["args_sha256"] == recorded[0]["args_sha256"]
    changed = client.post("/tools/salvar_minuta", headers=headers, json=write_body(context, corpus))
    assert changed.status_code == 409 and changed.json()["code"] == "idempotency_conflict"
    exhausted = client.post(
        "/tools/consultar_processo", headers={"X-Tool-Call-Id": "new"}, json=context
    )
    assert exhausted.status_code == 409 and exhausted.json()["code"] == "budget_exceeded"
    # Administrative repair of synthetic corpus; repeat the original operation/ID.
    if failure == "version_mismatch":
        with engine.begin() as conn:
            conn.execute(
                update(processes)
                .where(
                    processes.c.process_id == process.process_id,
                    processes.c.corpus_version == process.corpus_version,
                )
                .values(payload=process.model_dump(mode="json"))
            )
    else:
        ingest(engine, process, document, chunk_document(document))
    repaired = client.post("/tools/consultar_processo", headers=headers, json=context)
    assert repaired.status_code == 200
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(logical_tool_calls)
                .where(logical_tool_calls.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )
    assert [r["code"] for r in history(client, engine, context["run_id"])] == [
        failure,
        "idempotency_conflict",
        "budget_exceeded",
        None,
    ]


@pytest.mark.parametrize("denial", ["credential", "lease", "context", "grant"])
def test_unauthorized_call_never_reserves_or_reads_domain(
    client, context, engine, monkeypatch, denial
):
    def forbidden_domain(*args):
        raise AssertionError("Unauthorized request reached domain")

    monkeypatch.setattr(CorpusRepository, "process", forbidden_domain)
    body = dict(context)
    headers = {"X-Tool-Call-Id": "not-authorized"}
    if denial == "credential":
        headers["Authorization"] = "Bearer invalid-synthetic-token"
    elif denial == "lease":
        headers["X-Run-Token"] = "invalid-synthetic-lease"
    elif denial == "context":
        body["requirements_version"] = "OTHER"
    else:
        with engine.begin() as conn:
            worker = conn.execute(
                select(runs.c.worker_id).where(runs.c.run_id == context["run_id"])
            ).scalar_one()
            conn.execute(delete(permissions).where(permissions.c.principal_id == worker))
    result = client.post("/tools/consultar_processo", headers=headers, json=body)
    assert result.status_code == (401 if denial == "credential" else 403)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(logical_tool_calls)
                .where(logical_tool_calls.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )

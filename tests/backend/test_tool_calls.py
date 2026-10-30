"""Histórico de tentativas, correlação e orçamento das tools (A03, I1–I4)."""

import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import inspect, select

from agents.simulation import SimulationAdapter
from agents.worker import execute
from contracts.execution import ClaimedRun
from services.backend.migrate import migrate
from services.backend.schema import artifacts, events


def history(client, engine, run_id):
    with engine.connect() as conn:
        return client.app.state.execution.tool_call_history(conn, run_id)


def tool_events(engine, run_id):
    with engine.connect() as conn:
        return [
            row
            for row in conn.execute(
                select(events.c.kind, events.c.payload)
                .where(events.c.run_id == run_id)
                .order_by(events.c.sequence)
            ).mappings()
        ]


def write_body(context, corpus, key="draft-1", content="Minuta fictícia"):
    process, _ = corpus
    return {
        **context,
        "idempotency_key": key,
        "content": content,
        "evidence": [
            {
                "kind": "inventory",
                "process_id": process.process_id,
                "corpus_version": process.corpus_version,
            }
        ],
        "evidence_note": "Exportação parcial fictícia.",
    }


def test_every_attempt_is_recorded_with_correlation(client, engine, corpus, context):
    run_id = context["run_id"]
    missing = client.post(
        "/tools/ler_documento",
        headers={"X-Tool-Call-Id": "read-1"},
        json={**context, "document_id": "INEXISTENTE"},
    )
    assert missing.status_code == 404
    body = write_body(context, corpus)
    saved = client.post("/tools/salvar_minuta", headers={"X-Tool-Call-Id": "write-1"}, json=body)
    retried = client.post("/tools/salvar_minuta", headers={"X-Tool-Call-Id": "write-1"}, json=body)
    assert saved.status_code == retried.status_code == 200
    assert retried.json()["replayed"]

    rows = history(client, engine, run_id)
    assert [(r["tool_call_id"], r["attempt"], r["http_status"]) for r in rows] == [
        ("read-1", 1, 404),
        ("write-1", 1, 200),
        ("write-1", 2, 200),
    ]
    assert rows[0]["code"] == "not_found" and rows[0]["tool"] == "ler_documento"
    assert [r["replayed"] for r in rows] == [False, False, True]
    assert rows[1]["artifact_id"] == rows[2]["artifact_id"] == saved.json()["artifact_id"]
    assert all(r["duration_ms"] >= 0 and len(r["args_sha256"]) == 64 for r in rows)

    streamed = [e["payload"] for e in tool_events(engine, run_id) if e["kind"] == "tool"]
    assert [(e["tool_call_id"], e["status"]) for e in streamed] == [
        ("read-1", "error"),
        ("write-1", "ok"),
        ("write-1", "ok"),
    ]
    assert streamed[0]["code"] == "not_found" and streamed[2]["replayed"]


def test_rejected_input_and_rolled_back_write_are_audited(client, engine, corpus, context):
    run_id = context["run_id"]
    invalid = client.post(
        "/tools/buscar_documentos", headers={"X-Tool-Call-Id": "search-1"}, json=context
    )
    assert invalid.status_code == 422
    bad = write_body(context, corpus)
    bad["evidence"] = [{"document_id": "fake", "chunk_id": "fake", "page": 1}]
    assert client.post("/tools/salvar_minuta", json=bad).status_code == 422
    with engine.connect() as conn:
        assert conn.execute(select(artifacts).where(artifacts.c.run_id == run_id)).first() is None
    malformed = client.post(
        "/tools/consultar_processo", headers={"X-Tool-Call-Id": "id com espaco"}, json=context
    )
    assert malformed.status_code == 422

    rows = history(client, engine, run_id)
    assert [(r["tool"], r["http_status"], r["code"]) for r in rows] == [
        ("buscar_documentos", 422, "validation_error"),
        ("salvar_minuta", 422, "validation_error"),
        ("consultar_processo", 422, "validation_error"),
    ]
    assert rows[0]["tool_call_id"] == "search-1"
    assert rows[2]["tool_call_id"] != "id com espaco"


def test_only_the_lease_holder_writes_history(client, engine, context):
    run_id = context["run_id"]
    client.headers.pop("X-Run-Token")
    assert client.post("/tools/consultar_processo", json=context).status_code == 403
    forged = {"X-Run-Token": "reserva-forjada"}
    assert client.post("/tools/consultar_processo", headers=forged, json=context).status_code == 403
    assert client.post("/tools/buscar_documentos", json=context).status_code == 422
    assert history(client, engine, run_id) == []


def test_budget_counts_logical_calls_and_is_recorded(client, engine, context):
    service = client.app.state.execution
    service.max_tool_calls = 2
    calls = [("a", 200), ("b", 200), ("b", 200), ("c", 409)]
    for call_id, expected in calls:
        response = client.post(
            "/tools/consultar_processo", headers={"X-Tool-Call-Id": call_id}, json=context
        )
        assert response.status_code == expected, (call_id, response.text)
    assert response.json()["code"] == "budget_exceeded"
    rows = history(client, engine, context["run_id"])
    assert [(r["tool_call_id"], r["attempt"], r["code"]) for r in rows] == [
        ("a", 1, None),
        ("b", 1, None),
        ("b", 2, None),
        ("c", 1, "budget_exceeded"),
    ]


def test_attempt_after_finish_is_recorded_but_not_streamed(client, engine, context):
    run_id = context["run_id"]
    finished = client.post(
        f"/runs/{run_id}/result", json={"status": "failed", "error_code": "adapter_error"}
    )
    assert finished.status_code == 200
    late = client.post("/tools/consultar_processo", json=context)
    assert late.status_code == 409
    assert [r["code"] for r in history(client, engine, run_id)] == ["conflict"]
    assert tool_events(engine, run_id)[-1]["kind"] == "done"


def test_simulation_declares_the_calls_recorded_by_the_server(client, engine, corpus):
    process, _ = corpus
    created = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            "process_id": process.process_id,
            "corpus_version": process.corpus_version,
            "requirements_version": process.requirements_version,
            "task": "Benchmark sintético",
            "task_id": "DEV-001",
            "idempotency_key": str(uuid4()),
        },
    )
    assert created.status_code == 202
    claimed = client.post(
        "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
    ).json()

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            headers=client.worker_headers,
        ) as http:
            await execute(http, ClaimedRun.model_validate(claimed), SimulationAdapter())

    asyncio.run(run())
    run_id = claimed["run_id"]
    stored = client.get(f"/runs/{run_id}", headers=client.operator_headers).json()
    declared = stored["result"]["experiment"]["tool_calls"]
    recorded = history(client, engine, run_id)
    assert len(declared) == 4
    assert [c["tool_call_id"] for c in declared] == [r["tool_call_id"] for r in recorded]
    assert [c["tool"] for c in declared] == [r["tool"] for r in recorded]
    assert all(c["status"] == "ok" for c in declared)


def test_tool_calls_migration_round_trip(engine):
    assert "tool_calls" in inspect(engine).get_table_names()
    migrate(engine, "0003", downgrade=True)
    assert "tool_calls" not in inspect(engine).get_table_names()
    migrate(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("tool_calls")}
    assert {"tool_call_id", "attempt", "http_status", "args_sha256", "replayed"} <= columns

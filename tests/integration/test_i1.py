"""I1: identical logical requests, client parity and confirmed effects."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete, func, select

from agents import interface
from agents.interface import AsyncToolClient, ToolCallError, ToolClient
from contracts.catalog import TOOLS
from contracts.execution import ClaimedRun
from services.backend import execution as backend_execution
from services.backend.auth import authenticate
from services.backend.schema import artifacts, permissions, physical_tool_attempts
from tests.backend.test_tool_calls import write_body
from tests.integration.test_adapter_protocol import synthetic_execution


@pytest.fixture(autouse=True)
def retry_clock(monkeypatch):
    async def no_wait(_):
        return None

    monkeypatch.setattr(interface, "asyncio", SimpleNamespace(sleep=no_wait))
    monkeypatch.setattr(
        interface,
        "time",
        SimpleNamespace(
            sleep=lambda _: None,
            perf_counter=interface.time.perf_counter,
        ),
    )
    original = backend_execution.time
    now = original.time()
    monkeypatch.setattr(
        backend_execution,
        "time",
        SimpleNamespace(
            time=lambda: now,
            perf_counter=original.perf_counter,
        ),
    )


def execution(context, headers):
    return ClaimedRun(
        **(
            synthetic_execution().model_dump(mode="json")
            | {
                "run_id": context["run_id"],
                "context": context,
                "run_token": httpx.Headers(headers).get("X-Run-Token", "synthetic-lease"),
            }
        )
    )


def invoke(mode, context, headers, handler, name, arguments, records=None):
    records = records if records is not None else []
    if mode == "async":

        async def run():
            async with httpx.AsyncClient(
                base_url="http://test", headers=headers, transport=httpx.MockTransport(handler)
            ) as http:
                tools = AsyncToolClient(http, execution(context, headers))
                try:
                    return await tools.call(name, arguments)
                finally:
                    records.extend(tools.calls)

        return asyncio.run(run())
    tools = ToolClient("http://test", "unused", context, headers.get("X-Run-Token", "synthetic"))
    tools.client.close()
    tools.client = httpx.Client(
        base_url="http://test", headers=headers, transport=httpx.MockTransport(handler)
    )
    try:
        return tools.call(name, arguments)
    finally:
        records.extend(tools.calls)
        tools.close()


def process_response(context):
    return {
        **context,
        "process": {
            "process_id": context["process_id"],
            "corpus_version": context["corpus_version"],
            "requirements_version": context["requirements_version"],
            "title": "Synthetic",
            "export_completeness": "partial",
            "export_note": "Synthetic incomplete export",
        },
        "inventory": [],
    }


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_nested_mutation_after_commit_cannot_change_retry(mode, client, context, corpus, engine):
    body = write_body(context, corpus)
    arguments = {k: v for k, v in body.items() if k not in context}
    seen = []

    def respond(request):
        seen.append((request.headers["X-Tool-Call-Id"], request.content))
        result = client.post(
            request.url.path, content=request.content, headers=dict(request.headers)
        )
        if len(seen) == 1:
            assert result.status_code == 200
            arguments["evidence"][0]["process_id"] = "PRIVATE-I1-mutated"
            raise httpx.ReadTimeout("Synthetic loss after commit", request=request)
        return httpx.Response(result.status_code, json=result.json())

    records = []
    result = invoke(
        mode, context, dict(client.headers), respond, "salvar_minuta", arguments, records
    )
    assert len(seen) == 2 and len(set(seen)) == 1
    assert "error" not in result and result["replayed"] is True
    assert len(records) == 1 and records[0].status == "ok"
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
        physical = (
            conn.execute(
                select(physical_tool_attempts).where(
                    physical_tool_attempts.c.run_id == context["run_id"]
                )
            )
            .mappings()
            .all()
        )
    assert len(physical) == 2 and len({p["attempt_id"] for p in physical}) == 2
    assert len({p["tool_call_id"] for p in physical}) == 1
    assert all(p["client_received"] is None for p in physical)


@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize(
    "case,expected",
    [
        ("timeout", 2),
        ("lost_response", 2),
        ("storage", 2),
        ("quota_temporary", 2),
        ("revoked", 1),
        ("revoked_misflagged", 1),
        ("unauthorized", 1),
        ("conflict", 1),
        ("quota_permanent", 1),
        ("invalid_success", 1),
        ("exhausted", 3),
    ],
)
def test_clients_have_equivalent_retry_and_error_policy(mode, case, expected):
    context = synthetic_execution().context
    seen, records = [], []

    def respond(request):
        seen.append((request.headers["X-Tool-Call-Id"], request.content))
        if case == "invalid_success":
            return httpx.Response(200, json={"PRIVATE-I1": "invalid-success"})
        if len(seen) > 1 and case not in {"exhausted", "revoked_misflagged"}:
            return httpx.Response(200, json=process_response(context))
        if case in {"timeout", "lost_response"}:
            failure = httpx.ReadTimeout if case == "timeout" else httpx.ReadError
            raise failure("Synthetic transport loss", request=request)
        status, code, retryable = {
            "storage": (503, "storage_unavailable", True),
            "exhausted": (503, "storage_unavailable", True),
            "revoked": (403, "forbidden", False),
            "revoked_misflagged": (403, "forbidden", True),
            "unauthorized": (401, "unauthorized", False),
            "conflict": (409, "idempotency_conflict", False),
            "quota_permanent": (429, "resource_limit", False),
            "quota_temporary": (429, "resource_limit", True),
        }[case]
        return httpx.Response(
            status, json={"code": code, "message": "Synthetic", "retryable": retryable}
        )

    succeeds = case in {"timeout", "lost_response", "storage", "quota_temporary", "conflict"}
    if succeeds:
        result = invoke(mode, context, {}, respond, "consultar_processo", {}, records)
        assert ("error" in result) == (case == "conflict")
    else:
        with pytest.raises(ToolCallError) as failure:
            invoke(mode, context, {}, respond, "consultar_processo", {}, records)
        assert "PRIVATE-I1" not in str(failure.value)
    assert len(seen) == expected and len(set(seen)) == 1
    assert len(records) == 1 and records[0].tool_call_id == seen[0][0]


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_both_clients_consume_all_six_contracts(mode, client, context, corpus, engine):
    records, outputs = [], {}

    def respond(request):
        result = client.post(
            request.url.path, content=request.content, headers=dict(request.headers)
        )
        return httpx.Response(result.status_code, json=result.json())

    for name in TOOLS:
        arguments = {}
        if name == "buscar_documentos":
            arguments = {"query": "material"}
        elif name == "ler_documento":
            found = outputs["buscar_documentos"]["items"][0]
            arguments = {"document_id": found["document_id"], "pages": [found["page"]]}
        elif name in {"registrar_pendencia", "salvar_minuta"}:
            data = write_body(context, corpus)
            arguments = {k: v for k, v in data.items() if k not in context}
            if name == "registrar_pendencia":
                arguments["requirement_id"] = outputs["consultar_requisitos"]["items"][0][
                    "requirement_id"
                ]
        outputs[name] = invoke(
            mode, context, dict(client.headers), respond, name, arguments, records
        )
        TOOLS[name].output_model.model_validate(outputs[name])
    assert len(records) == 6 and all(r.status == "ok" for r in records)
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 2
        )


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_independent_calls_can_overlap_with_distinct_logical_ids(mode):
    context = synthetic_execution().context
    identities = []
    if mode == "sync":
        barrier = Barrier(2)

        def respond(request):
            identities.append(request.headers["X-Tool-Call-Id"])
            barrier.wait(timeout=5)
            return httpx.Response(200, json=process_response(context))

        tools = ToolClient("http://test", "synthetic-token", context, "synthetic-lease")
        tools.client.close()
        tools.client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond))
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: tools.call("consultar_processo", {}), range(2)))
            assert len(tools.calls) == 2
        finally:
            tools.close()
    else:

        async def run():
            together = asyncio.Event()

            async def respond(request):
                identities.append(request.headers["X-Tool-Call-Id"])
                if len(identities) == 2:
                    together.set()
                await asyncio.wait_for(together.wait(), timeout=5)
                return httpx.Response(200, json=process_response(context))

            async with httpx.AsyncClient(
                base_url="http://test", transport=httpx.MockTransport(respond)
            ) as http:
                tools = AsyncToolClient(http, execution(context, {}))
                return await asyncio.gather(
                    tools.call("consultar_processo", {}), tools.call("consultar_processo", {})
                )

        results = asyncio.run(run())
    assert len(results) == 2 and len(set(identities)) == 2


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_revocation_after_lost_receipt_stops_retry_without_duplicate_effect(
    mode, client, context, corpus, engine
):
    data = write_body(context, corpus)
    arguments = {k: v for k, v in data.items() if k not in context}
    actor = authenticate(engine, client.worker_headers["Authorization"])
    seen, records = [], []

    def respond(request):
        seen.append((request.headers["X-Tool-Call-Id"], request.content))
        response = client.post(
            request.url.path, content=request.content, headers=dict(request.headers)
        )
        if len(seen) == 1:
            assert response.status_code == 200
            with engine.begin() as conn:
                conn.execute(
                    delete(permissions).where(permissions.c.principal_id == actor["principal_id"])
                )
            raise httpx.ReadTimeout("Synthetic lost receipt before revocation", request=request)
        return httpx.Response(response.status_code, json=response.json())

    with pytest.raises(ToolCallError) as failure:
        invoke(mode, context, dict(client.headers), respond, "salvar_minuta", arguments, records)
    assert failure.value.response.status_code == 403
    assert len(seen) == 2 and len(set(seen)) == 1
    assert len(records) == 1 and records[0].status == "error" and records[0].artifact_id is None
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )

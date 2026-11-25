"""F6: full draft workflow and concurrent physical attempts after F5 extraction."""

import hashlib
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import delete, func, select

from contracts.models import ToolContext, WriteInput
from services.backend.artifact_integrity import validate_artifact
from services.backend.schema import artifacts, logical_tool_calls, requirements
from tests.backend.test_tool_calls import write_body


def send(client, name, body, call_id):
    return client.post(f"/tools/{name}", headers={"X-Tool-Call-Id": call_id}, json=body)


def test_search_read_draft_replay_keeps_scope_hash_and_physical_phases_without_checklist(
    client, context, corpus, engine
):
    with engine.begin() as conn:
        conn.execute(
            delete(requirements).where(
                requirements.c.process_id == context["process_id"],
                requirements.c.corpus_version == context["corpus_version"],
                requirements.c.requirements_version == context["requirements_version"],
            )
        )
    found = send(client, "buscar_documentos", {**context, "query": "material"}, "search-f6")
    assert found.status_code == 200 and found.json()["items"]
    chunk = found.json()["items"][0]
    read = send(
        client,
        "ler_documento",
        {**context, "document_id": chunk["document_id"], "pages": [chunk["page"]]},
        "read-f6",
    )
    assert read.status_code == 200 and read.json()["document"]["pages"][0]["text"]
    payload = {
        **write_body(context, corpus),
        "content": "  Minuta sintética F6.  ",
        "evidence": [{k: chunk[k] for k in ("document_id", "chunk_id", "page")}],
    }
    first = send(client, "salvar_minuta", payload, "draft-f6")
    second = send(client, "salvar_minuta", payload, "draft-f6")
    assert first.status_code == second.status_code == 200
    assert not first.json()["replayed"] and second.json() == {**first.json(), "replayed": True}
    normalized = WriteInput.model_validate(payload).model_dump(mode="json")
    assert (
        first.json()["content_sha256"] == hashlib.sha256(normalized["content"].encode()).hexdigest()
    )
    with engine.connect() as conn:
        stored = dict(
            conn.execute(select(artifacts).where(artifacts.c.run_id == context["run_id"]))
            .mappings()
            .one()
        )
        rows = client.app.state.execution.tracking.history(conn, context["run_id"])
        logical = (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .all()
        )
    validated = validate_artifact(
        stored, expected_tool="salvar_minuta", expected_context=ToolContext.model_validate(context)
    )
    fetched = client.get(
        f"/artifacts/{first.json()['artifact_id']}", headers=client.operator_headers
    )
    assert fetched.status_code == 200 and fetched.json() == validated.model_dump(mode="json")
    assert fetched.json()["payload"] == normalized and "requirement_id" not in normalized
    assert len(logical) == 3 and len(rows) == 4 and len({r["attempt_id"] for r in rows}) == 4
    writes = [r for r in rows if r["tool"] == "salvar_minuta"]
    assert len(writes) == 2 and all(r["tool_call_id"] == "draft-f6" for r in writes)
    assert sorted(r["phases"][1]["replayed"] for r in writes) == [False, True]
    assert all(r["phases"][1]["artifact_id"] == first.json()["artifact_id"] for r in writes)
    assert all(
        [p["phase"] for p in r["phases"]] == ["started", "effect_confirmed", "completed"]
        for r in writes
    )
    assert all(r["client_received"] is None for r in rows)


def test_concurrent_drafts_have_two_physical_attempts_and_one_artifact(
    client, context, corpus, engine
):
    payload = write_body(context, corpus)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(lambda _: send(client, "salvar_minuta", payload, "concurrent-f6"), range(2))
        )
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["artifact_id"] for r in responses}) == 1
    with engine.connect() as conn:
        rows = client.app.state.execution.tracking.history(conn, context["run_id"])
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                select(func.count())
                .select_from(logical_tool_calls)
                .where(logical_tool_calls.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    assert len(rows) == 2 and len({r["attempt_id"] for r in rows}) == 2
    assert sorted(r["phases"][1]["replayed"] for r in rows) == [False, True]
    assert all(r["http_status"] == 200 and r["client_received"] is None for r in rows)

"""E: reconcile JSONL with independent SQL reads, including failures invisible in SSE."""

import json
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

from scripts import export_chat
from services.backend.schema import (
    artifacts,
    events,
    logical_tool_calls,
    physical_tool_attempts,
    physical_tool_phases,
    runs,
    tool_calls,
)
from services.backend.tracking import ToolTracking
from tests.backend.test_a2 import call, result
from tests.backend.test_execution import scope, send
from tests.backend.test_tool_calls import write_body


def dump(engine, tmp_path, **filters):
    path = tmp_path / f"export-{uuid4()}.jsonl"
    count = export_chat.export_file(engine, path, kind="all", **filters)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert count == len(rows)
    return rows, path


def reconcile(engine, item):
    """No reuse of the exporter's history reader or projection for expected evidence."""
    rid, observed = item["run_id"], item["observed"]
    with engine.connect() as conn:
        logical = [
            dict(r)
            for r in conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == rid)
            ).mappings()
        ]
        assert sorted(logical, key=lambda r: r["tool_call_id"]) == observed["logical_calls"]
        physical = {
            r["attempt_id"]: dict(r)
            for r in conn.execute(
                select(physical_tool_attempts).where(physical_tool_attempts.c.run_id == rid)
            ).mappings()
        }
        assert set(physical) == {r["attempt_id"] for r in observed["physical_attempts"]}
        for attempt in observed["physical_attempts"]:
            assert {k: v for k, v in attempt.items() if k != "phases"} == physical[
                attempt["attempt_id"]
            ]
            phases = {
                r["phase"]: dict(r)
                for r in conn.execute(
                    select(physical_tool_phases).where(
                        physical_tool_phases.c.attempt_id == attempt["attempt_id"]
                    )
                ).mappings()
            }
            assert len(phases) == len(attempt["phases"])
            for phase in attempt["phases"]:
                assert {"attempt_id": attempt["attempt_id"], **phase} == phases[phase["phase"]]
        legacy = [
            dict(r)
            for r in conn.execute(
                select(tool_calls)
                .where(tool_calls.c.run_id == rid)
                .order_by(tool_calls.c.tool_call_id, tool_calls.c.attempt)
            ).mappings()
        ]
        assert legacy == observed["legacy_tool_stages"]
        stored = {
            r["artifact_id"]: dict(r)
            for r in conn.execute(select(artifacts).where(artifacts.c.run_id == rid)).mappings()
        }
        assert set(stored) == {r["artifact_id"] for r in observed["artifacts"]}
        for artifact in observed["artifacts"]:
            assert artifact == {
                k: v for k, v in stored[artifact["artifact_id"]].items() if k != "payload"
            }
        row = conn.execute(select(runs).where(runs.c.run_id == rid)).mappings().one()
        assert observed["status"] == row["status"]
        assert observed["finished_at"] == row["finished_at"]


def request(client, tool, body, identity="logical-write"):
    return client.post(f"/tools/{tool}", headers={"X-Tool-Call-Id": identity}, json=body)


@pytest.mark.parametrize("tool", ["registrar_pendencia", "salvar_minuta"])
def test_export_postcommit_retry_and_late_failure_without_sse(
    client, context, corpus, engine, tmp_path, tool
):
    body = write_body(context, corpus, content="PRIVATE-E-ARTIFACT")
    if tool == "registrar_pendencia":
        body["requirement_id"] = "REQ-DEMO-001"
    reads = []

    def lost_receipt(conn, cursor, statement, parameters, execution_context, many):
        if "FROM artifacts" in statement:
            reads.append(statement)
            if len(reads) == 3:
                raise SQLAlchemyError("PRIVATE-E-POSTCOMMIT")

    event.listen(engine, "before_cursor_execute", lost_receipt)
    try:
        assert request(client, tool, body).status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", lost_receipt)
    assert request(client, tool, body).json()["replayed"] is True
    assert (
        client.post(
            f"/runs/{context['run_id']}/result",
            json={"status": "failed", "error_code": "adapter_error"},
        ).status_code
        == 200
    )
    # No SSE notification exists for an attempt after terminal state.
    assert request(client, tool, body, "late-call").status_code == 409
    with engine.begin() as conn:
        conn.execute(
            delete(events).where(events.c.run_id == context["run_id"], events.c.kind == "tool")
        )
    items, path = dump(engine, tmp_path, run_id=context["run_id"])
    item = next(r for r in items if r["run_id"] == context["run_id"])
    reconcile(engine, item)
    observed = item["observed"]
    assert [a["http_status"] for a in observed["physical_attempts"]] == [503, 200, 409]
    assert len(observed["artifacts"]) == len(observed["logical_calls"]) == 1
    effects = [
        p
        for a in observed["physical_attempts"]
        for p in a["phases"]
        if p["phase"] == "effect_confirmed"
    ]
    assert [p["replayed"] for p in effects] == [False, True]
    assert {p["artifact_id"] for p in effects} == {observed["artifacts"][0]["artifact_id"]}
    assert all(a["client_received"] is None for a in observed["physical_attempts"])
    assert observed["physical_attempts"][-1]["started_at"] >= observed["finished_at"]
    assert "PRIVATE-E" not in path.read_text(encoding="utf-8")


def test_export_rollback_and_unknown_completion_preserve_nulls(
    client, context, corpus, engine, tmp_path
):
    def fail_effect(conn, cursor, statement, parameters, execution_context, many):
        if statement.startswith("INSERT INTO artifacts"):
            raise SQLAlchemyError("PRIVATE-E-ROLLBACK")

    event.listen(engine, "before_cursor_execute", fail_effect)
    try:
        assert request(client, "salvar_minuta", write_body(context, corpus)).status_code == 503
    finally:
        event.remove(engine, "before_cursor_execute", fail_effect)

    def lose_completion(conn, cursor, statement, parameters, execution_context, many):
        if statement.startswith("UPDATE physical_tool_attempts") and "http_status" in statement:
            raise SQLAlchemyError("PRIVATE-E-COLLECTOR")

    event.listen(engine, "before_cursor_execute", lose_completion)
    try:
        assert request(client, "consultar_processo", context, "unknown").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", lose_completion)
    # No trustworthy run attribution: this record must not leak into any run.
    orphan = ToolTracking(engine).begin("consultar_processo", "POST")
    items, _ = dump(engine, tmp_path, run_id=context["run_id"])
    item = next(r for r in items if r["run_id"] == context["run_id"])
    reconcile(engine, item)
    observed = item["observed"]
    assert observed["artifacts"] == []
    assert len(observed["logical_calls"]) == 2
    assert len(observed["physical_attempts"]) == 2
    assert orphan not in {a["attempt_id"] for a in observed["physical_attempts"]}
    unknown = next(a for a in observed["physical_attempts"] if a["tool_call_id"] == "unknown")
    assert unknown["http_status"] is unknown["finished_at"] is unknown["client_received"] is None
    assert [p["phase"] for p in unknown["phases"]] == ["started"]
    assert item["history_precision"]["total_physical_requests"] is None


@pytest.mark.parametrize("mixed", [False, True])
def test_legacy_stages_never_invent_physical_identity(client, context, engine, tmp_path, mixed):
    assert request(client, "consultar_processo", context, "legacy").status_code == 200
    with engine.begin() as conn:
        ids = select(physical_tool_attempts.c.attempt_id).where(
            physical_tool_attempts.c.run_id == context["run_id"]
        )
        conn.execute(delete(physical_tool_phases).where(physical_tool_phases.c.attempt_id.in_(ids)))
        conn.execute(
            delete(physical_tool_attempts).where(
                physical_tool_attempts.c.run_id == context["run_id"]
            )
        )
    if mixed:
        assert request(client, "consultar_processo", context, "legacy").status_code == 200
    items, _ = dump(engine, tmp_path, run_id=context["run_id"])
    item = next(r for r in items if r["run_id"] == context["run_id"])
    reconcile(engine, item)
    assert len(item["observed"]["physical_attempts"]) == int(mixed)
    assert len(item["observed"]["legacy_tool_stages"]) == 1 + int(mixed)
    assert item["history_precision"]["legacy"] == "stages_not_physical_requests"
    assert item["history_precision"]["total_physical_requests"] is None


def test_declaration_effect_and_evaluation_remain_separate(
    client, context, corpus, engine, tmp_path
):
    body = write_body(context, corpus, content="PRIVATE-E-CONTENT")
    receipt = request(client, "salvar_minuta", body).json()
    # Client may report an error even though an effect was observed.
    payload = result(context, [call("logical-write", "salvar_minuta", "error")], status="failed")
    payload["experiment"]["parameters"] = {"prompt": "PRIVATE-E-PARAMETERS"}
    assert client.post(f"/runs/{context['run_id']}/result", json=payload).status_code == 200
    items, path = dump(engine, tmp_path, run_id=context["run_id"])
    item = next(r for r in items if r["run_id"] == context["run_id"])
    reconcile(engine, item)
    declared = item["declared"]["experiment"]
    assert declared["tool_calls"] == payload["experiment"]["tool_calls"]
    assert declared["persisted_artifact_ids"] == []
    assert declared["cost_usd"] is declared["input_tokens"] is None
    assert item["observed"]["artifacts"][0]["artifact_id"] == receipt["artifact_id"]
    assert item["evaluated"] == {"verified_success": None, "evaluator": None}
    assert "PRIVATE-E" not in path.read_text(encoding="utf-8")
    private, _ = dump(engine, tmp_path, run_id=context["run_id"], include_content=True)
    full = next(r for r in private if r["run_id"] == context["run_id"])
    assert full["content"]["parameters"] == payload["experiment"]["parameters"]
    assert full["content"]["artifacts"][0]["payload"]["content"] == "PRIVATE-E-CONTENT"
    assert "lease_sha256" not in json.dumps(full) and "token_sha256" not in json.dumps(full)


def test_scope_kinds_empty_export_and_deterministic_output(
    client, context, corpus, engine, tmp_path
):
    participants = [str(uuid4()), str(uuid4())]
    chats = []
    for participant in participants:
        response = client.post(
            "/conversations",
            headers=client.operator_headers,
            json={**scope(corpus), "participant_id": participant},
        )
        cid = response.json()["conversation_id"]
        chats.append((cid, send(client, cid).json()["run_id"]))
    path = tmp_path / "default.jsonl"
    assert export_chat.export_file(engine, path, participant_id=participants[0]) == 1
    assert all(r["kind"] == "chat" for r in map(json.loads, path.read_text().splitlines()))
    items, first = dump(engine, tmp_path)
    assert {context["run_id"], *(r for _, r in chats)} <= {r["run_id"] for r in items}
    _, second = dump(engine, tmp_path)
    assert first.read_bytes() == second.read_bytes()
    scoped, _ = dump(engine, tmp_path, participant_id=participants[0])
    assert [r["run_id"] for r in scoped] == [chats[0][1]]
    empty, _ = dump(engine, tmp_path, participant_id=participants[0], conversation_id=chats[1][0])
    assert empty == []


def test_snapshot_is_stable_during_concurrent_write(client, context, engine, tmp_path):
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    aid = ToolTracking(engine).begin("consultar_processo", "POST")
    with engine.begin() as conn:
        conn.execute(
            update(physical_tool_attempts)
            .where(physical_tool_attempts.c.attempt_id == aid)
            .values(run_id=context["run_id"])
        )
    fired = False

    def concurrent(conn, cursor, statement, parameters, execution_context, many):
        nonlocal fired
        if not fired and statement.startswith("SELECT runs."):
            fired = True
            with engine.begin() as other:
                other.execute(
                    update(runs)
                    .where(runs.c.run_id == context["run_id"])
                    .values(status="failed", result={"error_code": "adapter_error"})
                )
                other.execute(
                    update(physical_tool_attempts)
                    .where(physical_tool_attempts.c.attempt_id == aid)
                    .values(http_status=503, response_state="prepared", finished_at=123.0)
                )
                other.execute(
                    insert(physical_tool_phases).values(
                        attempt_id=aid, phase="failed", recorded_at=123.0
                    )
                )

    event.listen(engine, "after_cursor_execute", concurrent)
    try:
        before, _ = dump(engine, tmp_path, run_id=context["run_id"])
    finally:
        event.remove(engine, "after_cursor_execute", concurrent)
    assert fired
    old = next(r for r in before if r["run_id"] == context["run_id"])
    assert old["observed"]["status"] == "running"
    assert old["observed"]["physical_attempts"][0]["http_status"] is None
    after, _ = dump(engine, tmp_path, run_id=context["run_id"])
    new = next(r for r in after if r["run_id"] == context["run_id"])
    assert new["observed"]["status"] == "failed"
    assert new["observed"]["physical_attempts"][0]["http_status"] == 503
    reconcile(engine, new)


@pytest.mark.parametrize("failure", ["sql", "serialization", "race"])
def test_failed_publication_never_leaves_partial_or_overwrites(
    engine, tmp_path, monkeypatch, failure
):
    path = tmp_path / "result.jsonl"

    def broken(*args, **kwargs):
        yield {"synthetic": "first record"}
        if failure == "sql":
            raise SQLAlchemyError("PRIVATE-E-SQL")
        if failure == "serialization":
            yield {"invalid": float("nan")}

    monkeypatch.setattr(export_chat, "records", broken)
    if failure == "race":
        original = export_chat.os.link

        def occupied(source, target):
            path.write_text("existing private file", encoding="utf-8")
            original(source, target)

        monkeypatch.setattr(export_chat.os, "link", occupied)
    with pytest.raises((SQLAlchemyError, ValueError, FileExistsError)):
        export_chat.export_file(engine, path)
    assert path.read_text() == "existing private file" if failure == "race" else not path.exists()
    assert list(tmp_path.glob(".export-*.tmp")) == []


def test_cli_selects_benchmark_and_reports_safe_failure(
    client, context, engine, tmp_path, monkeypatch, capsys
):
    path = tmp_path / "cli.jsonl"
    monkeypatch.setattr(export_chat, "make_engine", lambda: engine)
    monkeypatch.setattr(
        "sys.argv",
        ["export_chat", "--kind", "benchmark", "--run", context["run_id"], "--output", str(path)],
    )
    export_chat.main()
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["run_id"] == context["run_id"] and item["kind"] == "benchmark"
    assert "1 execuções" in capsys.readouterr().out

    def unavailable(*args, **kwargs):
        raise SQLAlchemyError("PRIVATE-E-CLI SQL credential")

    monkeypatch.setattr(export_chat, "export_file", unavailable)
    with pytest.raises(SystemExit) as exc:
        export_chat.main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "não concluída" in output.err and "PRIVATE-E" not in output.err + output.out


def test_structural_corruption_does_not_publish_unvalidated_receipt(
    client, context, corpus, engine, tmp_path
):
    receipt = request(client, "salvar_minuta", write_body(context, corpus)).json()
    with engine.begin() as conn:
        conn.execute(
            update(artifacts)
            .where(artifacts.c.artifact_id == receipt["artifact_id"])
            .values(receipt={**receipt, "unexpected": "PRIVATE-E-EXTRA"})
        )
    path = tmp_path / "corrupt.jsonl"
    with pytest.raises(ValueError):
        export_chat.export_file(engine, path, kind="all", run_id=context["run_id"])
    assert not path.exists() and list(tmp_path.glob(".export-*.tmp")) == []

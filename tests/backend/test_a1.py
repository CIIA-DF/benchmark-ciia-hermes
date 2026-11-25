"""A1: persisted artifact integrity and unchanged access rules over HTTP."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.exc import SQLAlchemyError

from contracts.models import ArtifactResponse, ToolError
from services.backend.auth import authenticate, provision
from services.backend.hashing import digest
from services.backend.schema import artifacts, permissions, principals, runs
from tests.backend.test_tool_calls import write_body


@pytest.fixture(params=["salvar_minuta", "registrar_pendencia"])
def saved(request, client, context, corpus):
    tool = request.param
    payload = write_body(context, corpus, content="PRIVATE-A1 synthetic content")
    if tool == "registrar_pendencia":
        payload["requirement_id"] = "REQ-DEMO-001"
    response = client.post(f"/tools/{tool}", json=payload)
    assert response.status_code == 200, response.text
    return tool, response.json()


def stored(engine, artifact_id):
    with engine.connect() as conn:
        return dict(
            conn.execute(select(artifacts).where(artifacts.c.artifact_id == artifact_id))
            .mappings()
            .one()
        )


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert ToolError.model_validate(response.json()).code == code
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A1" not in response.text


def test_get_rejects_corruption_for_each_writer(client, engine, context, saved, caplog):
    tool, receipt = saved
    aid = receipt["artifact_id"]
    url = f"/artifacts/{aid}"
    original = stored(engine, aid)
    before = client.get(url, headers=client.operator_headers)
    assert before.status_code == 200
    assert ArtifactResponse.model_validate(before.json()).tool == tool
    changes = []

    def changed(label, section, field, value, *, rehash=False):
        row = deepcopy(original)
        row[section][field] = value
        if rehash:
            row["input_sha256"] = digest(row["payload"])
        changes.append((label, row))

    changed("content", "payload", "content", "PRIVATE-A1 modified content")
    changed("canonical normalization", "payload", "content", "  PRIVATE-A1 padded  ", rehash=True)
    for field, value in {
        "run_id": str(uuid4()),
        "process_id": "PRIVATE-A1-other",
        "corpus_version": "PRIVATE-A1-other",
        "requirements_version": "PRIVATE-A1-other",
    }.items():
        changed(f"payload {field}", "payload", field, value, rehash=True)
        changed(f"receipt {field}", "receipt", field, value)
    changed("artifact identity", "receipt", "artifact_id", str(uuid4()))
    changed("content hash", "receipt", "content_sha256", "0" * 64)
    changed("stored replay", "receipt", "replayed", True)
    for label, values in {
        "input hash": {"input_sha256": "0" * 64},
        "idempotency key": {"idempotency_key": "PRIVATE-A1-other"},
        "unsupported tool": {"tool": "PRIVATE-A1-other"},
        "opposite tool": {
            "tool": "registrar_pendencia" if tool == "salvar_minuta" else "salvar_minuta"
        },
        "null payload": {"payload": None},
        "null receipt": {"receipt": None},
    }.items():
        changes.append((label, {**original, **values}))

    for label, row in changes:
        updates = {
            key: row[key]
            for key in ("tool", "payload", "receipt", "input_sha256", "idempotency_key")
        }
        with engine.begin() as conn:
            conn.execute(update(artifacts).where(artifacts.c.artifact_id == aid).values(**updates))
        try:
            result = client.get(url, headers=client.operator_headers)
            assert result.status_code == 500, label
            assert_error(result, 500, "invalid_response")
            assert stored(engine, aid) == row, label
        finally:
            with engine.begin() as conn:
                conn.execute(
                    update(artifacts)
                    .where(artifacts.c.artifact_id == aid)
                    .values(**{key: original[key] for key in updates})
                )
    assert "PRIVATE-A1" not in caplog.text
    assert client.get(url, headers=client.operator_headers).json() == before.json()


def test_get_preserves_access_and_reads_without_active_lease(
    client, engine, context, corpus, saved
):
    _, receipt = saved
    aid = receipt["artifact_id"]
    url = f"/artifacts/{aid}"
    original = stored(engine, aid)
    assert_error(client.get(url, headers={"Authorization": ""}), 401, "unauthorized")
    assert_error(client.get(url), 403, "forbidden")
    assert_error(
        client.get(f"/artifacts/{uuid4()}", headers=client.operator_headers), 404, "not_found"
    )
    assert_error(
        client.get("/artifacts/not-a-uuid", headers=client.operator_headers),
        422,
        "validation_error",
    )
    other_token = uuid4().hex
    provision(
        engine,
        "a1-other-" + uuid4().hex,
        other_token,
        "operator",
        [(context["process_id"], context["corpus_version"])],
    )
    other_headers = {"Authorization": "Bearer " + other_token}
    # Authorization takes precedence even when the artifact itself is corrupt.
    with engine.begin() as conn:
        conn.execute(update(artifacts).where(artifacts.c.artifact_id == aid).values(receipt=None))
    assert_error(client.get(url, headers=other_headers), 404, "not_found")
    assert_error(client.get(url), 403, "forbidden")
    with engine.begin() as conn:
        conn.execute(
            update(artifacts)
            .where(artifacts.c.artifact_id == aid)
            .values(receipt=original["receipt"])
        )
        conn.execute(
            update(runs)
            .where(runs.c.run_id == context["run_id"])
            .values(status="timed_out", lease_until=0)
        )
    # Reading confirmed effects does not require can_write or a live worker lease.
    actor = authenticate(engine, client.operator_headers["Authorization"])

    with engine.begin() as conn:
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == actor["principal_id"])
            .values(can_write=False)
        )
    result = client.get(url, headers=client.operator_headers)
    assert result.status_code == 200 and result.json()["receipt"] == receipt
    assert result.headers["cache-control"] == "no-store"
    with engine.begin() as conn:
        conn.execute(delete(permissions).where(permissions.c.principal_id == actor["principal_id"]))
    assert_error(client.get(url, headers=client.operator_headers), 403, "forbidden")
    assert stored(engine, aid) == original


def test_get_validates_trusted_run_context_and_row_identity(client, engine, context, corpus):
    response = client.post("/tools/salvar_minuta", json=write_body(context, corpus))
    assert response.status_code == 200
    url = f"/artifacts/{response.json()['artifact_id']}"
    variants = [
        None,
        [],
        {"run_id": context["run_id"]},
        {**context, "requirements_version": None},
        {**context, "requirements_version": "  " + context["requirements_version"] + "  "},
        {**context, "run_id": str(uuid4())},
    ]
    for bad in variants:
        with engine.begin() as conn:
            conn.execute(update(runs).where(runs.c.run_id == context["run_id"]).values(context=bad))
        try:
            assert_error(client.get(url, headers=client.operator_headers), 500, "invalid_response")
        finally:
            with engine.begin() as conn:
                conn.execute(
                    update(runs).where(runs.c.run_id == context["run_id"]).values(context=context)
                )
    other = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            **{k: context[k] for k in ("process_id", "corpus_version", "requirements_version")},
            "task": "Synthetic A1 other run",
            "task_id": "A1",
            "idempotency_key": str(uuid4()),
        },
    )
    assert other.status_code == 202
    aid = response.json()["artifact_id"]
    with engine.begin() as conn:
        conn.execute(
            update(artifacts)
            .where(artifacts.c.artifact_id == aid)
            .values(run_id=other.json()["run_id"])
        )
    try:
        assert_error(client.get(url, headers=client.operator_headers), 500, "invalid_response")
    finally:
        with engine.begin() as conn:
            conn.execute(
                update(artifacts)
                .where(artifacts.c.artifact_id == aid)
                .values(run_id=context["run_id"])
            )
    assert client.get(url, headers=client.operator_headers).status_code == 200


def test_get_database_failure_stays_safe_503(client, engine):
    def unavailable(conn, cursor, statement, parameters, execution_context, many):
        if "FROM artifacts" in statement:
            raise SQLAlchemyError("PRIVATE-A1 storage failure")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        assert_error(
            client.get(f"/artifacts/{uuid4()}", headers=client.operator_headers),
            503,
            "storage_unavailable",
        )
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)

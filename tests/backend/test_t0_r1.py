"""HTTP regressions for revocation between durable reservation and write effect."""

import pytest
from sqlalchemy import func, select, update

from services.backend.schema import artifacts, logical_tool_calls, principals, runs
from tests.backend.test_tool_calls import history, write_body


@pytest.mark.parametrize("tool", ["registrar_pendencia", "salvar_minuta"])
@pytest.mark.parametrize("target", ["worker_id", "owner_id"])
def test_revoked_write_between_reservation_and_effect_is_audited(
    client, corpus, context, engine, monkeypatch, tool, target
):
    service = client.app.state.execution
    original = service.write_artifact
    with engine.connect() as conn:
        principal_id = conn.execute(
            select(getattr(runs.c, target)).where(runs.c.run_id == context["run_id"])
        ).scalar_one()
    body = write_body(context, corpus)
    if tool == "registrar_pendencia":
        body["requirement_id"] = "REQ-DEMO-001"
    seen = []

    def revoked(*args, **kwargs):
        # This hook runs after ToolService has committed the logical reservation.
        with engine.begin() as conn:
            assert (
                conn.execute(
                    select(func.count())
                    .select_from(logical_tool_calls)
                    .where(logical_tool_calls.c.run_id == context["run_id"])
                ).scalar_one()
                == 1
            )
            conn.execute(
                update(principals)
                .where(principals.c.principal_id == principal_id)
                .values(can_write=False)
            )
        seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "write_artifact", revoked)
    headers = {"X-Tool-Call-Id": "revoked-write"}
    response = client.post(f"/tools/{tool}", headers=headers, json=body)
    assert seen == [True]
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"
    assert "artifact_id" not in response.json() and "persisted_at" not in response.json()
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )
        assert (
            conn.execute(
                select(func.count())
                .select_from(logical_tool_calls)
                .where(logical_tool_calls.c.run_id == context["run_id"])
            ).scalar_one()
            == 1
        )
    records = history(client, engine, context["run_id"])
    assert len(records) == 1 and records[0]["http_status"] == 403
    assert records[0]["code"] == "forbidden" and records[0]["artifact_id"] is None
    # Explicit restoration permits the same operation, without freeing its logical ID.
    monkeypatch.setattr(service, "write_artifact", original)
    with engine.begin() as conn:
        conn.execute(
            update(principals)
            .where(principals.c.principal_id == principal_id)
            .values(can_write=True)
        )
    response = client.post(f"/tools/{tool}", headers=headers, json=body)
    assert response.status_code == 200 and not response.json()["replayed"]
    replay = client.post(f"/tools/{tool}", headers=headers, json=body)
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["artifact_id"] == response.json()["artifact_id"]
    assert [r["http_status"] for r in history(client, engine, context["run_id"])] == [403, 200, 200]


@pytest.mark.parametrize(
    ("target", "change"),
    [
        ("worker_id", {"role": "operator"}),
        ("worker_id", {"executor": "langgraph"}),
        ("owner_id", {"role": "worker"}),
    ],
)
def test_current_profile_role_and_executor_are_rechecked(
    client, corpus, context, engine, monkeypatch, target, change
):
    service = client.app.state.execution
    original = service.write_artifact

    def changed(*args, **kwargs):
        with engine.begin() as conn:
            principal_id = conn.execute(
                select(getattr(runs.c, target)).where(runs.c.run_id == context["run_id"])
            ).scalar_one()
            conn.execute(
                update(principals).where(principals.c.principal_id == principal_id).values(**change)
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "write_artifact", changed)
    response = client.post("/tools/salvar_minuta", json=write_body(context, corpus))
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(artifacts)
                .where(artifacts.c.run_id == context["run_id"])
            ).scalar_one()
            == 0
        )
    assert history(client, engine, context["run_id"])[0]["code"] == "forbidden"

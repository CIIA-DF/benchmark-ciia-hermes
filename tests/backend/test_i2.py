"""I2: bootstrap never restores revoked grants or overwrites an administrative rotation."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from scripts import chat
from scripts import provision as provision_cli
from services.backend.app import create_app
from services.backend.auth import (
    authenticate,
    authorize,
    bootstrap,
    identity_state,
    provision,
    rotate_token,
    token_hash,
)
from services.backend.errors import ToolFailure
from services.backend.migrate import migrate
from services.backend.schema import administrative_events, principals
from services.backend.storage import make_engine
from tests.backend.test_a3 import body, send
from tests.backend.test_tool_calls import write_body


@pytest.fixture(autouse=True)
def isolated_bootstrap_environment(monkeypatch):
    monkeypatch.delenv("BACKEND_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("BACKEND_WORKER_TOKEN", raising=False)


def test_revocation_survives_restart_and_old_environment(client, corpus, engine, monkeypatch):
    process = corpus[0]
    token = "synthetic-old-operator-token-123456789"
    monkeypatch.setenv("BACKEND_OPERATOR_TOKEN", token)
    monkeypatch.delenv("BACKEND_WORKER_TOKEN", raising=False)
    bootstrap(engine)
    provision(engine, "local-operator", token, "operator", [], can_write=False)
    # A fresh application/engine runs initialization and bootstrap again.
    with TestClient(create_app(make_engine(engine.url))) as restarted:
        denied = restarted.post(
            "/runs", json=body(corpus), headers={"Authorization": "Bearer " + token}
        )
        assert denied.status_code == 403
    actor = authenticate(engine, "Bearer " + token)
    assert actor["can_write"] is False
    # A revoked principal cannot submit a task after initialization repeats.
    denied = send(client, body(corpus), headers={"Authorization": "Bearer " + token})
    assert denied.status_code == 403
    with pytest.raises(ToolFailure):
        with engine.connect() as conn:
            authorize(conn, actor["principal_id"], process.process_id, process.corpus_version)
    with pytest.raises(ToolFailure):
        with engine.connect() as conn:
            authorize(conn, actor["principal_id"], "PROC-DEMO-001", "synthetic-v1")


def snapshot(engine, principal_id):
    with engine.connect() as conn:
        row = (
            conn.execute(select(principals).where(principals.c.principal_id == principal_id))
            .mappings()
            .one()
        )
        return dict(row), identity_state(conn, row)


def audits(engine, principal_id):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                select(administrative_events).where(
                    administrative_events.c.principal_id == principal_id
                )
            ).mappings()
        ]


@pytest.mark.parametrize("role", ["operator", "worker"])
def test_rotation_preserves_revoked_profile_and_survives_stale_environment(
    engine, monkeypatch, role
):
    env = "BACKEND_OPERATOR_TOKEN" if role == "operator" else "BACKEND_WORKER_TOKEN"
    name = "local-operator" if role == "operator" else "simulation-worker"
    old, new = uuid4().hex, uuid4().hex
    monkeypatch.setenv(env, old)
    bootstrap(engine)
    provision(
        engine,
        name,
        old,
        role,
        [],
        can_write=False,
        executor="simulation" if role == "worker" else None,
    )
    before = snapshot(engine, name)[1]
    rotate_token(engine, name, new)
    with TestClient(create_app(make_engine(engine.url))):
        pass
    assert snapshot(engine, name)[1] == before
    assert authenticate(engine, "Bearer " + new)["can_write"] is False
    with pytest.raises(ToolFailure) as revoked:
        authenticate(engine, "Bearer " + old)
    assert revoked.value.status == 401
    row = next(item for item in audits(engine, name) if item["operation"] == "rotate")
    assert row["before_state"] == row["after_state"] == before
    assert row["credential_changed"] is True
    encoded = json.dumps(audits(engine, name))
    assert old not in encoded and new not in encoded and token_hash(new) not in encoded
    assert "token_sha256" not in encoded


def test_bootstrap_race_creates_one_identity_and_one_event(engine, monkeypatch):
    monkeypatch.setenv("BACKEND_OPERATOR_TOKEN", uuid4().hex)
    monkeypatch.delenv("BACKEND_WORKER_TOKEN", raising=False)
    # local-operator tem nome fixo; num PostgreSQL reaproveitado ele já existe, e o bootstrap
    # não deve gravar nada. Num banco novo, a corrida cria uma identidade e um evento.
    before = {item["event_id"] for item in audits(engine, "local-operator")}
    expected = 0 if before else 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: bootstrap(engine), range(2)))
    assert len([e for e in audits(engine, "local-operator") if e["event_id"] not in before]) == (
        expected
    )
    bootstrap(engine)
    assert len([e for e in audits(engine, "local-operator") if e["event_id"] not in before]) == (
        expected
    )


@pytest.mark.parametrize("operation", ["update", "rotate"])
def test_audit_failure_rolls_back_credentials_grants_and_profile(engine, operation):
    old, new = uuid4().hex, uuid4().hex
    profile = f"rollback-profile-{uuid4().hex[:10]}"
    provision(engine, profile, old, "operator", [("PROC-SYNTHETIC", "v1")], can_write=True)
    before = snapshot(engine, profile)

    def unavailable(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO administrative_events"):
            raise SQLAlchemyError("PRIVATE-I2 audit failure")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        with pytest.raises(SQLAlchemyError):
            if operation == "rotate":
                rotate_token(engine, profile, new)
            else:
                provision(engine, profile, new, "operator", [], can_write=False)
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert snapshot(engine, profile) == before
    assert len(audits(engine, profile)) == 1


def test_cli_requires_explicit_update_and_rotation_preserves_state(
    engine, tmp_path, monkeypatch, capsys
):
    name, old, new = "cli-profile", uuid4().hex, uuid4().hex
    provision(engine, name, old, "operator", [], can_write=False)
    config = tmp_path / "private.json"
    monkeypatch.setenv("SYNTHETIC_I2_TOKEN", new)
    monkeypatch.setattr(provision_cli, "make_engine", lambda: engine)
    config.write_text(
        json.dumps(
            [
                {
                    "principal_id": name,
                    "token_env": "SYNTHETIC_I2_TOKEN",
                    "role": "operator",
                    "grants": [],
                    "can_write": True,
                }
            ]
        )
    )
    monkeypatch.setattr("sys.argv", ["provision", str(config)])
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    assert refused.value.code == 2 and snapshot(engine, name)[0]["token_sha256"] == token_hash(old)
    monkeypatch.setattr("sys.argv", ["provision", str(config), "--operation", "update"])
    provision_cli.main()
    assert authenticate(engine, "Bearer " + new)["can_write"] is True
    config.write_text(json.dumps([{"principal_id": name, "token_env": "SYNTHETIC_I2_TOKEN"}]))
    monkeypatch.setenv("SYNTHETIC_I2_TOKEN", old)
    monkeypatch.setattr("sys.argv", ["provision", str(config), "--operation", "rotate"])
    provision_cli.main()
    assert authenticate(engine, "Bearer " + old)["can_write"] is True
    output = capsys.readouterr()
    assert new not in output.out + output.err and old not in output.out + output.err


@pytest.mark.parametrize("bad", ["coerced_bool", "extra_secret", "rotation_profile"])
def test_cli_rejects_invalid_configuration_without_echoing_secrets(
    engine, tmp_path, monkeypatch, capsys, bad
):
    config = tmp_path / "private.json"
    token = "PRIVATE-I2-secret-token-never-echo-12345"
    monkeypatch.setenv("SYNTHETIC_I2_TOKEN", token)
    identity = {
        "principal_id": "invalid-cli",
        "token_env": "SYNTHETIC_I2_TOKEN",
        "role": "operator",
        "grants": [],
    }
    operation = "create"
    if bad == "coerced_bool":
        identity["can_write"] = 1
    elif bad == "extra_secret":
        identity["token"] = token
    else:
        operation = "rotate"
    config.write_text(json.dumps([identity]))
    monkeypatch.setattr("sys.argv", ["provision", str(config), "--operation", operation])
    monkeypatch.setattr(
        provision_cli, "make_engine", lambda: pytest.fail("Must validate before database")
    )
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    assert refused.value.code == 2
    output = capsys.readouterr()
    assert "PRIVATE-I2" not in output.out + output.err


def test_migration_preserves_profiles_and_does_not_invent_legacy_events(engine):
    token = uuid4().hex
    provision(engine, "legacy-profile", token, "operator", [], can_write=False)
    before = snapshot(engine, "legacy-profile")
    migrate(engine, "0008", downgrade=True)
    assert "administrative_events" not in inspect(engine).get_table_names()
    migrate(engine)
    assert snapshot(engine, "legacy-profile") == before and audits(engine, "legacy-profile") == []


def test_rotated_credential_is_revalidated_between_reservation_and_effect(
    client, context, corpus, engine, monkeypatch
):
    actor = authenticate(engine, client.worker_headers["Authorization"])
    service = client.app.state.execution
    original = service.write_artifact

    def rotated(*args, **kwargs):
        rotate_token(engine, actor["principal_id"], uuid4().hex)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "write_artifact", rotated)
    response = client.post("/tools/salvar_minuta", json=write_body(context, corpus))
    assert response.status_code == 403 and response.json()["code"] == "forbidden"
    from services.backend.schema import artifacts

    with engine.connect() as conn:
        assert (
            conn.execute(select(artifacts).where(artifacts.c.run_id == context["run_id"])).first()
            is None
        )


def test_repeating_private_setup_does_not_restore_revoked_rights(engine, tmp_path, monkeypatch):
    root = tmp_path / "synthetic-setup"
    root.mkdir()
    (root / "portal").mkdir()
    original_load = chat.load
    monkeypatch.setattr(chat, "ROOT", root)
    monkeypatch.setattr(chat, "CONFIG", root / "chat.env")
    monkeypatch.setattr(chat, "load", lambda: original_load(chat.CONFIG))
    for key in (
        "POSTGRES_USER",
        "POSTGRES_DB",
        "POSTGRES_PASSWORD",
        "BACKEND_OPERATOR_TOKEN",
        "BACKEND_WORKER_TOKEN",
        "BACKEND_URL",
    ):
        # Track initially absent keys too, so chat.load's setdefault cannot leak to later tests.
        monkeypatch.setenv(key, "synthetic-placeholder")
        monkeypatch.delenv(key)
    chat.setup()
    bootstrap(engine)
    token = os.environ["BACKEND_OPERATOR_TOKEN"]
    provision(engine, "local-operator", token, "operator", [], can_write=False)
    paths = [chat.CONFIG, root / "portal/.env.local"]
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
    chat.setup()
    assert [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths] == before
    with TestClient(create_app(make_engine(engine.url))) as restarted:
        result = restarted.get("/capabilities", headers={"Authorization": "Bearer " + token})
        assert result.status_code == 200 and result.json()["can_write"] is False
    actor = authenticate(engine, "Bearer " + token)
    with engine.connect() as conn:
        with pytest.raises(ToolFailure):
            authorize(conn, actor["principal_id"], "PROC-DEMO-001", "synthetic-v1")


@pytest.mark.parametrize("fault", [ValueError, SQLAlchemyError, OSError])
def test_cli_connection_configuration_failure_never_echoes_private_details(
    tmp_path, monkeypatch, capsys, fault
):
    config = tmp_path / "private.json"
    config.write_text(
        json.dumps(
            [
                {
                    "principal_id": "safe-failure",
                    "token_env": "SYNTHETIC_I2_TOKEN",
                    "role": "operator",
                    "grants": [],
                    "can_write": False,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SYNTHETIC_I2_TOKEN", "synthetic-safe-failure-token-123456789")
    monkeypatch.setattr("sys.argv", ["provision", str(config)])

    def broken_engine():
        raise fault("PRIVATE-I2-connection-configuration")

    monkeypatch.setattr(provision_cli, "make_engine", broken_engine)
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    assert refused.value.code == 2
    output = capsys.readouterr()
    assert "PRIVATE-I2" not in output.out + output.err


# --- Revisão de 21/11: lote sem aplicação parcial e aviso do bootstrap ------------------


def profile_file(tmp_path, monkeypatch, names, tokens=None, **fields):
    """Um token_env por perfil; tokens distintos salvo quando o teste repete de propósito."""
    tokens = tokens or [uuid4().hex for _ in names]
    entries = []
    for index, (name, token) in enumerate(zip(names, tokens, strict=True)):
        env = f"SYNTHETIC_BATCH_TOKEN_{index}"
        monkeypatch.setenv(env, token)
        entries.append({"principal_id": name, "token_env": env, **fields})
    config = tmp_path / "batch.json"
    config.write_text(json.dumps(entries), encoding="utf-8")
    return config, tokens


@pytest.mark.parametrize("operation", ["create", "update", "rotate"])
def test_cli_batch_is_checked_before_any_write(engine, tmp_path, monkeypatch, capsys, operation):
    # IDs únicos: a suíte também roda em PostgreSQL compartilhado.
    suffix = uuid4().hex[:8]
    existing_id, new_id = f"batch-existing-{suffix}", f"batch-new-{suffix}"
    present = [existing_id]
    old = uuid4().hex
    provision(engine, existing_id, old, "operator", [], can_write=False)
    before_events = len(audits(engine, existing_id))
    # create: o perfil novo vem antes do existente; update/rotate: o existente vem antes do ausente.
    names = [new_id, *present] if operation == "create" else [*present, new_id]
    fields = {} if operation == "rotate" else {"role": "operator", "grants": [], "can_write": False}
    config, tokens = profile_file(tmp_path, monkeypatch, names, **fields)
    monkeypatch.setattr(provision_cli, "make_engine", lambda: engine)
    monkeypatch.setattr("sys.argv", ["provision", str(config), "--operation", operation])
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    assert refused.value.code == 2
    output = capsys.readouterr()
    assert "Perfis aplicados: 0 de 2" in output.err
    assert "batch-" not in output.err and not any(t in output.err for t in tokens)
    with engine.connect() as conn:
        created = conn.execute(
            select(principals).where(principals.c.principal_id == new_id)
        ).first()
    assert created is None and audits(engine, new_id) == []
    assert snapshot(engine, existing_id)[0]["token_sha256"] == token_hash(old)
    assert len(audits(engine, existing_id)) == before_events


@pytest.mark.parametrize("repeated", ["identity", "credential"])
def test_cli_rejects_repeated_identity_or_credential_before_database(
    tmp_path, monkeypatch, repeated
):
    token = uuid4().hex
    if repeated == "identity":
        args = (["dup", "dup"], None)
    else:
        args = (["dup-a", "dup-b"], [token, token])
    config, _ = profile_file(
        tmp_path, monkeypatch, *args, role="operator", grants=[], can_write=False
    )
    monkeypatch.setattr("sys.argv", ["provision", str(config)])
    monkeypatch.setattr(
        provision_cli, "make_engine", lambda: pytest.fail("Must validate before database")
    )
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    assert refused.value.code == 2


def test_cli_batch_create_applies_all_when_none_exist(engine, tmp_path, monkeypatch):
    suffix = uuid4().hex[:8]
    names = [f"batch-a-{suffix}", f"batch-b-{suffix}"]
    config, _ = profile_file(
        tmp_path, monkeypatch, names, role="operator", grants=[], can_write=False
    )
    monkeypatch.setattr(provision_cli, "make_engine", lambda: engine)
    monkeypatch.setattr("sys.argv", ["provision", str(config)])
    provision_cli.main()
    assert [len(audits(engine, name)) for name in names] == [1, 1]


def test_bootstrap_warns_when_environment_token_differs(engine, monkeypatch, caplog):
    stored, stale = uuid4().hex, uuid4().hex
    # Em PostgreSQL compartilhado o perfil local pode já existir: fixe o token gravado antes.
    provision(engine, "local-operator", stored, "operator", [], can_write=False)
    monkeypatch.setenv("BACKEND_OPERATOR_TOKEN", stored)
    bootstrap(engine)
    before = snapshot(engine, "local-operator")
    caplog.set_level("WARNING", logger="services.backend.auth")
    bootstrap(engine)
    assert "bootstrap_token_mismatch" not in caplog.text
    monkeypatch.setenv("BACKEND_OPERATOR_TOKEN", stale)
    bootstrap(engine)
    assert "bootstrap_token_mismatch principal_id=local-operator" in caplog.text
    assert stale not in caplog.text and token_hash(stale) not in caplog.text
    assert stored not in caplog.text and token_hash(stored) not in caplog.text
    # O perfil continua preservado: o aviso não rotaciona nem restaura nada.
    assert snapshot(engine, "local-operator") == before


# --- Segunda revisão de 21/11: conferência de perfil/credencial e can_write explícito -------


def run_cli(tmp_path, monkeypatch, entries, tokens, operation="create", engine=None):
    """Executa o CLI com entradas livres; cada entrada usa o token_env de mesmo índice."""
    for index, token in enumerate(tokens):
        monkeypatch.setenv(f"SYNTHETIC_REVIEW_TOKEN_{index}", token)
    payload = [
        {**entry, "token_env": f"SYNTHETIC_REVIEW_TOKEN_{index}"}
        for index, entry in enumerate(entries)
    ]
    config = tmp_path / "review.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    factory = (lambda: engine) if engine is not None else (lambda: pytest.fail("Banco tocado"))
    monkeypatch.setattr(provision_cli, "make_engine", factory)
    monkeypatch.setattr("sys.argv", ["provision", str(config), "--operation", operation])
    with pytest.raises(SystemExit) as refused:
        provision_cli.main()
    return refused.value.code


def exists(engine, principal_id):
    with engine.connect() as conn:
        found = conn.execute(select(principals).where(principals.c.principal_id == principal_id))
        return found.first() is not None


def test_cli_refuses_invalid_profile_in_batch_before_database(tmp_path, monkeypatch):
    suffix = uuid4().hex[:8]
    entries = [
        {"principal_id": f"op-{suffix}", "role": "operator", "grants": [], "can_write": False},
        # Worker sem executor: antes era recusado só dentro do laço, depois do primeiro commit.
        {"principal_id": f"wk-{suffix}", "role": "worker", "grants": [], "can_write": False},
    ]
    code = run_cli(tmp_path, monkeypatch, entries, [uuid4().hex, uuid4().hex])
    assert code == 2


@pytest.mark.parametrize("operation", ["create", "rotate"])
def test_cli_refuses_credential_of_another_profile_before_any_write(
    engine, tmp_path, monkeypatch, capsys, operation
):
    suffix = uuid4().hex[:8]
    owner_token, first_old = uuid4().hex, uuid4().hex
    provision(engine, f"owner-{suffix}", owner_token, "operator", [], can_write=False)
    if operation == "create":
        entries = [
            {
                "principal_id": f"new-a-{suffix}",
                "role": "operator",
                "grants": [],
                "can_write": False,
            },
            {
                "principal_id": f"new-b-{suffix}",
                "role": "operator",
                "grants": [],
                "can_write": False,
            },
        ]
    else:
        provision(engine, f"new-a-{suffix}", first_old, "operator", [], can_write=False)
        provision(engine, f"new-b-{suffix}", uuid4().hex, "operator", [], can_write=False)
        entries = [{"principal_id": f"new-a-{suffix}"}, {"principal_id": f"new-b-{suffix}"}]
    # O segundo perfil reaproveita a credencial de owner: colisão no índice único do hash.
    code = run_cli(tmp_path, monkeypatch, entries, [uuid4().hex, owner_token], operation, engine)
    assert code == 2
    assert "Perfis aplicados: 0 de 2" in capsys.readouterr().err
    if operation == "create":
        assert not exists(engine, f"new-a-{suffix}") and not exists(engine, f"new-b-{suffix}")
    else:
        assert snapshot(engine, f"new-a-{suffix}")[0]["token_sha256"] == token_hash(first_old)
    assert authenticate(engine, "Bearer " + owner_token)["principal_id"] == f"owner-{suffix}"


def test_cli_update_requires_explicit_can_write(engine, tmp_path, monkeypatch):
    name, token = f"writer-{uuid4().hex[:8]}", uuid4().hex
    provision(engine, name, token, "operator", [], can_write=True)
    entries = [{"principal_id": name, "role": "operator", "grants": []}]
    # Sem can_write, o update antes gravava False e revogava a escrita em silêncio.
    code = run_cli(tmp_path, monkeypatch, entries, [uuid4().hex], "update")
    assert code == 2
    assert snapshot(engine, name)[0]["can_write"] is True

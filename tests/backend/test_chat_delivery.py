import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from agents.registry import load_adapter
from contracts.catalog import TOOLS, tool_catalog
from contracts.models import ToolContext
from scripts.export_chat import export_file
from services.backend.app import create_app
from services.backend.migrate import migrate
from services.backend.schema import conversations
from services.backend.storage import make_engine


def test_catalog_hides_privileged_context_and_preserves_argument_constraints():
    catalog = {item["name"]: item for item in tool_catalog()}
    assert set(catalog) == set(TOOLS)
    for item in catalog.values():
        schema = item["parameters"]
        assert not set(ToolContext.model_fields) & schema["properties"].keys()
        assert not set(ToolContext.model_fields) & set(schema["required"])
        assert schema["additionalProperties"] is False
    assert catalog["buscar_documentos"]["parameters"]["properties"]["limit"]["maximum"] == 20
    assert "requirement_id" in catalog["registrar_pendencia"]["parameters"]["required"]
    assert catalog["salvar_minuta"]["parameters"]["properties"]["evidence"]["minItems"] == 1


@pytest.mark.parametrize("executor", ["hermes", "langgraph"])
def test_real_executor_requires_real_factory(executor):
    with pytest.raises(ValueError, match="exige fábrica"):
        load_adapter(executor)
    with pytest.raises(ValueError, match="Simulação"):
        load_adapter(executor, "agents.simulation:SimulationAdapter")
    with pytest.raises(ValueError, match="inicializar"):
        load_adapter(executor, "agents.missing_runtime:factory")


def test_participant_survives_restart_and_is_not_agent_context(client, corpus, engine):
    participant = str(uuid4())
    scope = {
        key: getattr(corpus[0], key)
        for key in ("process_id", "corpus_version", "requirements_version")
    }
    created = client.post(
        "/conversations",
        headers=client.operator_headers,
        json={**scope, "participant_id": participant},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["conversation_id"]
    other = client.post(
        "/conversations",
        headers=client.operator_headers,
        json={**scope, "participant_id": str(uuid4())},
    ).json()
    response = client.get(
        "/conversations", headers=client.operator_headers, params={"participant_id": participant}
    )
    assert [row["conversation_id"] for row in response.json()] == [cid]
    # O filtro é conveniência: não representa uma identidade autenticada diferente.
    assert (
        client.get(
            f"/conversations/{other['conversation_id']}", headers=client.operator_headers
        ).status_code
        == 200
    )
    sent = client.post(
        f"/conversations/{cid}/messages",
        headers=client.operator_headers,
        json={"content": "Pergunta fictícia", "idempotency_key": str(uuid4())},
    )
    run_id = sent.json()["run_id"]
    claimed = client.post(
        "/runs/claim",
        headers=client.worker_headers,
        json={"executor": "simulation", "run_id": run_id},
    ).json()
    assert participant not in json.dumps(claimed)
    headers = {**client.worker_headers, "X-Run-Token": claimed["run_token"]}
    assert (
        client.post(
            f"/runs/{run_id}/result",
            headers=headers,
            json={"status": "succeeded", "answer": "Resposta fictícia"},
        ).status_code
        == 200
    )
    # Nova engine + aplicação, sem seed: prova persistência fora da conexão original.
    reopened = make_engine(engine.url)
    with TestClient(create_app(reopened)) as reader:
        detail = reader.get(f"/conversations/{cid}", headers=client.operator_headers).json()
        assert detail["participant_id"] == participant
        assert [message["content"] for message in detail["messages"]] == [
            "Pergunta fictícia",
            "Resposta fictícia",
        ]
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(conversations.c.participant_id).where(conversations.c.conversation_id == cid)
            ).scalar_one()
            == participant
        )


def test_export_is_scoped_and_omits_content_and_credentials(client, corpus, engine, tmp_path):
    participant = str(uuid4())
    scope = {
        key: getattr(corpus[0], key)
        for key in ("process_id", "corpus_version", "requirements_version")
    }
    cid = client.post(
        "/conversations",
        headers=client.operator_headers,
        json={**scope, "participant_id": participant},
    ).json()["conversation_id"]
    sent = client.post(
        f"/conversations/{cid}/messages",
        headers=client.operator_headers,
        json={"content": "CONTEUDO-FICTICIO-PRIVADO", "idempotency_key": str(uuid4())},
    )
    run_id = sent.json()["run_id"]
    claimed = client.post(
        "/runs/claim",
        headers=client.worker_headers,
        json={"executor": "simulation", "run_id": run_id},
    ).json()
    headers = {**client.worker_headers, "X-Run-Token": claimed["run_token"]}
    receipt = client.post(
        "/tools/salvar_minuta",
        headers=headers,
        json={
            **claimed["context"],
            "idempotency_key": "export",
            "content": "MINUTA-FICTICIA-PRIVADA",
            "evidence_note": "NOTA-FICTICIA-PRIVADA",
            "evidence": [
                {
                    "kind": "inventory",
                    "process_id": scope["process_id"],
                    "corpus_version": scope["corpus_version"],
                }
            ],
        },
    ).json()
    client.post(
        f"/runs/{run_id}/result",
        headers=headers,
        json={"status": "succeeded", "answer": "RESPOSTA-FICTICIA-PRIVADA"},
    )
    path = tmp_path / "summary.jsonl"
    assert export_file(engine, path, participant_id=participant) == 1
    raw = path.read_text(encoding="utf-8")
    item = json.loads(raw)
    assert "PRIVAD" not in raw
    assert claimed["run_token"] not in raw
    assert client.worker_headers["Authorization"].split()[1] not in raw
    assert item["input_tokens"] is None and item["cost_usd"] is None
    assert item["receipts"][0]["artifact_id"] == receipt["artifact_id"]
    assert item["participant_id"] == participant
    with pytest.raises(FileExistsError):
        export_file(engine, path, participant_id=participant)
    assert path.read_text(encoding="utf-8") == raw
    private = tmp_path / "private.jsonl"
    assert export_file(engine, private, conversation_id=cid, include_content=True) == 1
    assert json.loads(private.read_text(encoding="utf-8"))["content"]["task"] == (
        "CONTEUDO-FICTICIO-PRIVADO"
    )
    assert export_file(engine, tmp_path / "empty.jsonl", participant_id=uuid4()) == 0
    snapshot = client.get(f"/runs/{run_id}", headers=client.operator_headers).json()
    assert snapshot["artifacts"] == [
        {"artifact_id": receipt["artifact_id"], "tool": "salvar_minuta"}
    ]


def test_participant_upgrade_preserves_legacy_conversation(tmp_path):
    database = make_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    migrate(database, "0002")
    with database.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "INSERT INTO principals (principal_id, token_sha256, role, can_write) "
                "VALUES ('test', 'not-a-credential', 'operator', 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO conversations "
                "(conversation_id, owner_id, process_id, corpus_version, requirements_version, "
                "executor, created_at) VALUES ('legacy', 'test', 'p', 'v', 'r', 'simulation', 1)"
            )
        )
    migrate(database)
    with database.connect() as conn:
        row = conn.execute(select(conversations)).mappings().one()
        assert row["conversation_id"] == "legacy"
        assert row["participant_id"] is None
    migrate(database, "0002", downgrade=True)
    assert "participant_id" not in {
        c["name"] for c in inspect(database).get_columns("conversations")
    }
    database.dispose()

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from pipelines.documents.ingest import chunk_document, load_fixture
from scripts.checklist import import_checklist
from scripts.demo import ROOT
from services.backend.app import create_app
from services.backend.auth import provision
from services.backend.storage import ingest, initialize, make_engine


@pytest.fixture
def corpus():
    process, document = load_fixture(ROOT / "examples")
    # IDs únicos continuam úteis em testes que criam engines próprios fora da fixture.
    suffix = uuid4().hex[:10]
    process = process.model_copy(update={"process_id": f"PROC-{suffix}"})
    document = document.model_copy(update={"process_id": process.process_id})
    return process, document


@pytest.fixture
def engine(tmp_path):
    base = os.getenv("TEST_DATABASE_URL")
    if base is None:
        database = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
        initialize(database)
        yield database
        database.dispose()
        return
    # PostgreSQL: um schema novo por teste isola dados e migrações sem apagar o banco. O
    # search_path vai na URL porque vários testes recriam engines (e um subprocesso) a partir
    # de engine.url; um listener de conexão se perderia nesses caminhos.
    schema = f"t_{uuid4().hex}"
    url = make_url(base)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    database = make_engine(url.update_query_dict({"options": f"-csearch_path={schema}"}))
    try:
        initialize(database)
        yield database
    finally:
        database.dispose()
        with admin.connect() as conn:
            conn.execute(text("SET lock_timeout = '10s'"))
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.fixture
def client(engine, corpus):
    process, document = corpus
    ingest(engine, process, document, chunk_document(document))
    import_checklist(
        engine,
        process.process_id,
        process.corpus_version,
        process.requirements_version,
        [
            {
                "requirement_id": "REQ-DEMO-001",
                "description": "Checklist fictício de teste",
                "source": "Fixture sintética",
            }
        ],
    )
    suffix = uuid4().hex
    operator_token, worker_token = uuid4().hex, uuid4().hex
    grants = [(process.process_id, process.corpus_version)]
    provision(engine, "operator-" + suffix, operator_token, "operator", grants, can_write=True)
    provision(
        engine,
        "worker-" + suffix,
        worker_token,
        "worker",
        grants,
        can_write=True,
        executor="simulation",
    )
    with TestClient(create_app(engine)) as instance:
        instance.operator_headers = {"Authorization": "Bearer " + operator_token}
        instance.worker_headers = {"Authorization": "Bearer " + worker_token}
        instance.headers.update(instance.worker_headers)
        yield instance


@pytest.fixture
def context(corpus, client):
    process, _ = corpus
    scope = {
        "process_id": process.process_id,
        "corpus_version": process.corpus_version,
        "requirements_version": process.requirements_version,
    }
    response = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            **scope,
            "task": "Tarefa fictícia",
            "task_id": "DEV-001",
            "idempotency_key": str(uuid4()),
        },
    )
    assert response.status_code == 202, response.text
    claim = client.post(
        "/runs/claim", headers=client.worker_headers, json={"executor": "simulation"}
    )
    assert claim.status_code == 200, claim.text
    value = claim.json()
    client.headers["X-Run-Token"] = value["run_token"]
    return value["context"]

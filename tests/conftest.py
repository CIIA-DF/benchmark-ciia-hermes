import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from pipelines.documents.ingest import chunk_document, load_fixture
from scripts.demo import ROOT
from services.backend.app import create_app
from services.backend.storage import ingest, initialize, make_engine


@pytest.fixture
def corpus():
    process, document = load_fixture(ROOT / "examples")
    # IDs únicos permitem rodar contra PostgreSQL sem apagar tabelas ou dados existentes.
    suffix = uuid4().hex[:10]
    process = process.model_copy(update={"process_id": f"PROC-{suffix}"})
    document = document.model_copy(update={"process_id": process.process_id})
    return process, document


@pytest.fixture
def engine(tmp_path):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    database = make_engine(url)
    initialize(database)
    yield database
    database.dispose()


@pytest.fixture
def client(engine, corpus):
    process, document = corpus
    ingest(engine, process, document, chunk_document(document))
    with TestClient(create_app(engine)) as instance:
        yield instance


@pytest.fixture
def context(corpus):
    process, _ = corpus
    return {
        "run_id": str(uuid4()),
        "process_id": process.process_id,
        "corpus_version": process.corpus_version,
        "requirements_version": process.requirements_version,
    }

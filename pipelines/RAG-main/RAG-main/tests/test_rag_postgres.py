import json
import os
import re
from uuid import uuid4

import pytest
from app.config import RetrievalMode, Settings
from app.db.models import Chunk, Document, Embedding, Process
from app.db.session import IndexConfigurationError, initialize_database, session_factory
from app.ingestion.chunking import chunk_document
from app.ingestion.indexing import IndexExport, ParsedExport, index_exports
from app.main import create_app
from app.retrieval.keyword_search import keyword_search
from app.retrieval.service import RetrievalService
from app.retrieval.vector_search import vector_search
from app.schemas.query import QueryRequest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateSchema, DropSchema

PROCESS_A = "00000-00000001/2025-01"
PROCESS_B = "00000-00000002/2025-02"


class SyntheticEncoder:
    def __init__(self, spec):
        self.spec = spec
        self.calls = []

    def encode(self, texts):
        self.calls.extend(texts)
        return [[1, 0, 0] if "laborat" in text else [0, 1, 0] for text in texts]


@pytest.fixture
def database():
    url = os.getenv("RAG_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina RAG_TEST_DATABASE_URL para validar PostgreSQL com pgvector.")
    schema = f"rag_test_{uuid4().hex}"
    admin = create_engine(url, hide_parameters=True)
    engine = create_engine(
        url, hide_parameters=True, connect_args={"options": f"-csearch_path={schema},public"}
    )
    settings = Settings(
        _env_file=None,
        embedding_model="test/encoder",
        embedding_revision="a" * 40,
        embedding_dimensions=3,
        chunk_tokens=10,
        chunk_overlap=2,
    )
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        initialize_database(engine, settings)
        yield engine, settings
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def prepare(tmp_path, process, *texts):
    path = tmp_path / "entrada.documentos.jsonl"
    documents = [
        {
            "processo_sei": process,
            "arquivo_origem": "exportacao-sintetica.pdf",
            "pagina_inicio": page,
            "pagina_fim": page,
            "documento_sei_id": str(123455 + page),
            "tipo_documento": "Despacho",
            "paginas": [{"pagina": page, "texto_limpo": text}],
        }
        for page, text in enumerate(texts, start=1)
    ]
    path.write_text("\n".join(map(json.dumps, documents)), encoding="utf-8")
    export = ParsedExport.from_jsonl(path)
    chunks = [
        chunk
        for doc in export.documents
        for chunk in chunk_document(
            doc,
            lambda text: [m.span() for m in re.finditer(r"\S+", text)],
            chunk_tokens=10,
            overlap=2,
        )
    ]
    return IndexExport(export, chunks)


@pytest.fixture
def corpus(database, tmp_path):
    engine, settings = database
    encoder = SyntheticEncoder(settings.embedding)
    sessions = session_factory(engine)
    exports = [
        prepare(
            tmp_path,
            PROCESS_A,
            "Aquisição de materiais de laboratório.",
            "Férias e afastamento de servidores.",
        ),
        prepare(tmp_path, PROCESS_B, "Aquisição para outro laboratório."),
    ]
    summary = index_exports(sessions, settings, encoder, exports)
    assert summary["embeddings_generated"] == 3
    return engine, settings, sessions, encoder, exports


def test_index_idempotente_e_substitui_apenas_exportacao_informada(corpus, tmp_path):
    engine, settings, sessions, encoder, exports = corpus
    initialize_database(engine, settings)
    assert index_exports(sessions, settings, encoder, exports)["embeddings_reused"] == 3
    assert len(encoder.calls) == 3

    updated = prepare(tmp_path, PROCESS_A, "Compra de computadores novos.")
    summary = index_exports(sessions, settings, encoder, [updated])
    assert summary["embeddings_generated"] == 1
    with sessions() as session:
        assert [
            session.scalar(select(func.count()).select_from(model))
            for model in (Process, Document, Chunk, Embedding)
        ] == [2, 2, 2, 2]
        assert set(session.scalars(select(Chunk.chunk_id))) == {
            updated.chunks[0].chunk_id,
            exports[1].chunks[0].chunk_id,
        }
    with pytest.raises(IndexConfigurationError):
        initialize_database(engine, settings.model_copy(update={"chunk_tokens": 9}))


def test_indice_preserva_exportacao_anterior_quando_falha(corpus, tmp_path):
    _, settings, sessions, encoder, exports = corpus
    updated = prepare(tmp_path, PROCESS_A, "Conteúdo diferente.")
    encoder.encode = lambda texts: [[0, 1]]
    with pytest.raises(IntegrityError):
        index_exports(sessions, settings, encoder, [updated])
    with sessions() as session:
        assert set(session.scalars(select(Chunk.chunk_id))) == {
            chunk.chunk_id for export in exports for chunk in export.chunks
        }


def test_busca_vetorial_textual_e_identificadores(corpus):
    _, _, sessions, encoder, _ = corpus
    with sessions() as session:
        request = QueryRequest(question="laboratórios", processo_sei=PROCESS_A)
        hits = vector_search(session, request, encoder, 1)
        assert len(hits) == 1
        assert hits[0].vector_score == pytest.approx(1)
        assert hits[0].paginas_origem == [1]
        assert hits[0].documento_sei_id == "123456"
        assert keyword_search(session, request, 5)[0].keyword_score > 0

        request = QueryRequest(
            question="Qual a evidência do documento 123457?", processo_sei=PROCESS_A
        )
        hits = keyword_search(session, request, 5)
        assert hits[0].documento_sei_id == "123457" and hits[0].exact_identifier_match
        request = QueryRequest(
            question=f"Consulte o processo {PROCESS_B}", documento_sei_id="123456"
        )
        hits = keyword_search(session, request, 1)
        assert hits[0].processo_sei == PROCESS_B and hits[0].exact_identifier_match
        assert keyword_search(session, QueryRequest(question="a e o"), 5) == []


def test_api_query_valida_filtros_e_modos(corpus):
    engine, settings, sessions, encoder, _ = corpus
    app = create_app(settings, engine=engine)
    app.state.retrieval = RetrievalService(
        sessions, settings, encoder, lambda pairs: [3.0] * len(pairs)
    )
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/api/query", json={"question": "   "}).status_code == 422
        invalid = client.post(
            "/api/query", json={"question": "teste", "processo_sei": "valor-invalido"}
        )
        assert invalid.status_code == 422 and "valor-invalido" not in invalid.text
        body = {"question": "laboratórios", "processo_sei": PROCESS_B, "top_k": 1}
        for mode in RetrievalMode:
            response = client.post("/api/query", json={**body, "mode": mode})
            assert response.status_code == 200
            payload = response.json()
            assert payload["mode"] == mode
            (hit,) = payload["results"]
            assert hit["processo_sei"] == PROCESS_B and hit["pagina_inicio"] == 1
            assert hit["vector_score"] == pytest.approx(1)
            assert (hit["rrf_score"] is not None) == (mode != RetrievalMode.DENSE)
            assert (hit["rerank_score"] is not None) == (mode == RetrievalMode.HYBRID_RERANK)
        response = client.post("/api/query", json={**body, "documento_sei_id": "999999"})
        assert response.status_code == 200 and response.json()["results"] == []

        app.state.retrieval = RetrievalService(
            sessions, settings.model_copy(update={"rerank_enabled": False}), encoder
        )
        result = client.post("/api/query", json={**body, "mode": RetrievalMode.HYBRID_RERANK})
        assert result.json()["mode"] == RetrievalMode.HYBRID

        app.state.retrieval = RetrievalService(
            sessions, settings.model_copy(update={"chunk_tokens": 9}), encoder
        )
        assert client.get("/health").status_code == 503
        assert client.post("/api/query", json=body).status_code == 503

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from contracts.models import DocumentResult, ProcessResult, SearchResult
from pipelines.documents.ingest import chunk_document
from services.backend.app import create_app
from services.backend.storage import chunks, ingest, make_engine


def test_ingest_commit_reconnect_and_api(engine, corpus, context, client):
    process, document = corpus
    items = chunk_document(document)
    ingest(engine, process, document, items)
    # Reabrir a engine evita confundir sucesso declarado com persistência confirmada.
    url = engine.url
    engine.dispose()
    reopened = make_engine(url)
    with TestClient(create_app(reopened), headers=dict(client.headers)) as client:
        response = client.post("/tools/consultar_processo", json=context)
        assert response.status_code == 200
        assert ProcessResult.model_validate(response.json()).process == process
        result = SearchResult.model_validate(
            client.post(
                "/tools/buscar_documentos",
                json={**context, "query": "material"},
            ).json()
        )
        assert result.items
        read = DocumentResult.model_validate(
            client.post(
                "/tools/ler_documento",
                json={**context, "document_id": document.document_id},
            ).json()
        )
        assert read.document == document
        pages = {page.number: page.text for page in read.document.pages}
        for item in result.items:
            assert pages[item.page][item.start : item.end] == item.text
        assert ingest(reopened, process, document, items) == 0
        with reopened.connect() as connection:
            count = connection.execute(
                select(func.count())
                .select_from(chunks)
                .where(
                    chunks.c.process_id == process.process_id,
                )
            ).scalar_one()
            assert count == len(items)

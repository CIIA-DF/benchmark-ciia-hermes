import pytest

from contracts.models import Document, SearchInput, ToolError
from pipelines.documents.ingest import chunk_document
from services.backend.storage import ingest


def test_search_is_scoped_to_process_and_corpus(client, engine, corpus, context):
    process, document = corpus
    other_process = process.model_copy(update={"process_id": process.process_id + "-other"})
    other_doc = document.model_copy(update={"process_id": other_process.process_id})
    ingest(engine, other_process, other_doc, chunk_document(other_doc))
    response = client.post("/tools/buscar_documentos", json={**context, "query": "material"})
    assert response.status_code == 200
    result = response.json()
    assert result["items"]
    assert {item["process_id"] for item in result["items"]} == {process.process_id}
    assert result["export_completeness"] == "partial"
    assert result["run_id"] == context["run_id"]
    missing = client.post(
        "/tools/buscar_documentos",
        json={
            **context,
            "corpus_version": "not-imported",
            "query": "material",
        },
    )
    assert missing.status_code == 403


def test_literal_search_and_empty_result_caveat(client, context):
    for term in ["%", "_", "termo inexistente"]:
        response = client.post("/tools/buscar_documentos", json={**context, "query": term})
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert "não prova" in response.json()["warning"]


def test_errors_do_not_echo_inputs_and_unauthorized_context_is_rejected(client, context):
    bad = client.post(
        "/tools/buscar_documentos", json={**context, "query": " ", "secret": "nunca-ecoar"}
    )
    assert bad.status_code == 422
    assert "nunca-ecoar" not in bad.text
    assert ToolError.model_validate(bad.json()).code == "validation_error"
    wrong_version = client.post(
        "/tools/consultar_processo",
        json={
            **context,
            "requirements_version": "wrong",
        },
    )
    assert wrong_version.status_code == 403
    for tool in ["registrar_pendencia", "salvar_minuta"]:
        response = client.post(
            f"/tools/{tool}",
            json={
                **context,
                "idempotency_key": "attempt-1",
                "content": "Texto fictício",
                "evidence": [],
                "evidence_note": "Demonstração sem ação autorizada.",
            },
        )
        assert response.status_code == 422
        assert response.json()["code"] == "validation_error"


def test_contract_rejects_invalid_limits_and_duplicate_pages(context, corpus):
    for limit in [0, 21]:
        with pytest.raises(ValueError):
            SearchInput(**context, query="material", limit=limit)
    raw = corpus[1].model_dump()
    raw["pages"].append(raw["pages"][0])
    with pytest.raises(ValueError):
        Document.model_validate(raw)


def test_read_rejects_document_from_another_process(client, engine, corpus, context):
    process, document = corpus
    other_process = process.model_copy(update={"process_id": process.process_id + "-separate"})
    other_doc = document.model_copy(
        update={
            "process_id": other_process.process_id,
            "document_id": "ONLY-OTHER-PROCESS",
        }
    )
    ingest(engine, other_process, other_doc, chunk_document(other_doc))
    response = client.post(
        "/tools/ler_documento",
        json={
            **context,
            "document_id": other_doc.document_id,
        },
    )
    assert response.status_code == 404
    assert "pages" not in response.json()


def test_requirements_return_versioned_synthetic_checklist(client, context):
    response = client.post("/tools/consultar_requisitos", json=context)
    assert response.status_code == 200
    assert response.json()["requirements_version"] == context["requirements_version"]
    assert response.json()["items"][0]["requirement_id"] == "REQ-DEMO-001"

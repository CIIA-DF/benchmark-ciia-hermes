"""Integrated acceptance for scoped document reads and page identity."""

from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import ToolCallError, tool_outcome
from services.backend.corpus import CorpusRepository
from services.backend.schema import logical_tool_calls
from services.backend.storage import documents
from tests.backend.test_tool_calls import history


def read(client, context, document_id, pages=None):
    return client.post(
        "/tools/ler_documento", json={**context, "document_id": document_id, "pages": pages}
    )


def test_inventory_and_search_feed_full_and_partial_reads(client, corpus, context):
    process = client.post("/tools/consultar_processo", json=context)
    assert process.status_code == 200
    document_id = process.json()["inventory"][0]["document_id"]
    found = client.post("/tools/buscar_documentos", json={**context, "query": "material"})
    assert found.status_code == 200 and found.json()["items"]
    chunk = found.json()["items"][0]
    selected = read(client, context, chunk["document_id"], [chunk["page"]])
    assert selected.status_code == 200
    assert selected.json()["document"]["document_id"] == document_id
    assert [p["number"] for p in selected.json()["document"]["pages"]] == [chunk["page"]]
    complete = read(client, context, document_id)
    assert complete.status_code == 200
    expected = corpus[1].model_dump(mode="json")
    assert complete.json()["document"] == expected
    numbers = [p["number"] for p in expected["pages"]]
    reversed_request = read(client, context, document_id, list(reversed(numbers)))
    assert reversed_request.status_code == 200
    assert reversed_request.json()["document"] == expected
    assert selected.json()["document"]["sha256"] == expected["sha256"]
    assert selected.json()["requirements_version"] == context["requirements_version"]


@pytest.mark.parametrize(
    "corruption",
    ["document_id", "process_id", "corpus_version", "duplicates", "order", "missing_pages", "null"],
)
def test_corrupt_document_is_safe_and_audited(client, corpus, context, engine, corruption):
    original = corpus[1].model_dump(mode="json")
    payload = deepcopy(original)
    payload["title"] = "SYNTHETIC-PRIVATE-DOCUMENT"
    if corruption in {"document_id", "process_id", "corpus_version"}:
        payload[corruption] = "SYNTHETIC-PRIVATE-IDENTITY"
    elif corruption == "duplicates":
        payload["pages"] = [payload["pages"][0], payload["pages"][0]]
    elif corruption == "order":
        payload["pages"] = list(reversed(payload["pages"]))
    elif corruption == "missing_pages":
        payload.pop("pages")
    else:
        payload = None
    with engine.begin() as conn:
        conn.execute(
            update(documents)
            .where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
                documents.c.document_id == original["document_id"],
            )
            .values(payload=payload)
        )
    result = read(client, context, original["document_id"])
    assert result.status_code == 500 and result.json()["code"] == "invalid_response"
    assert not result.json()["retryable"] and "SYNTHETIC-PRIVATE" not in result.text
    attempts = history(client, engine, context["run_id"])
    assert len(attempts) == 1 and attempts[0]["http_status"] == 500
    assert attempts[0]["code"] == "invalid_response"
    with engine.connect() as conn:
        assert (
            conn.execute(
                select(logical_tool_calls).where(logical_tool_calls.c.run_id == context["run_id"])
            )
            .mappings()
            .one()["args_sha256"]
            == attempts[0]["args_sha256"]
        )


def test_missing_and_invalid_pages_have_distinct_codes(client, corpus, context):
    document_id = corpus[1].document_id
    assert read(client, context, "MISSING").status_code == 404
    assert read(client, context, document_id, [999]).status_code == 404
    for pages in ([], [0], [1, 1], [True], ["1"]):
        result = read(client, context, document_id, pages)
        assert result.status_code == 422 and result.json()["code"] == "validation_error"


def test_page_numbers_need_not_be_contiguous(client, corpus, context, engine):
    payload = corpus[1].model_dump(mode="json")
    payload["pages"][1]["number"] = 7
    with engine.begin() as conn:
        conn.execute(
            update(documents)
            .where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
                documents.c.document_id == payload["document_id"],
            )
            .values(payload=payload)
        )
    result = read(client, context, payload["document_id"], [7, 1])
    assert result.status_code == 200
    assert [p["number"] for p in result.json()["document"]["pages"]] == [1, 7]
    assert read(client, context, payload["document_id"], [2]).status_code == 404


def test_service_rejects_wrong_document_and_extra_pages(
    client, corpus, context, monkeypatch, engine
):
    original = corpus[1].model_dump(mode="json")
    for key in ("document", "pages"):
        payload = deepcopy(original)
        if key == "document":
            payload["document_id"] = "OTHER"
        monkeypatch.setattr(CorpusRepository, "read", lambda *args, payload=payload: payload)
        result = read(client, context, original["document_id"], [1])
        assert result.status_code == 500 and result.json()["code"] == "invalid_response"
    assert all(a["http_status"] == 500 for a in history(client, engine, context["run_id"]))


def test_client_rejects_foreign_context_document_and_page_substitution(client, corpus, context):
    document_id = corpus[1].document_id
    good = read(client, context, document_id, [1]).json()
    expected = {**context, "document_id": document_id, "pages": [1]}
    variants = []
    for key in ("run_id", "process_id", "corpus_version", "requirements_version"):
        value = deepcopy(good)
        value[key] = str(uuid4()) if key == "run_id" else "OTHER"
        if key in {"process_id", "corpus_version"}:
            value["document"][key] = "OTHER"
        variants.append(value)
    value = deepcopy(good)
    value["document"]["document_id"] = "OTHER"
    variants.append(value)
    value = deepcopy(good)
    value["document"]["pages"][0]["number"] = 2
    variants.append(value)
    full = read(client, context, document_id).json()
    variants.append(full)
    value = deepcopy(full)
    value["document"]["pages"].reverse()
    variants.append(value)
    value = deepcopy(good)
    value["document"]["pages"] *= 2
    variants.append(value)
    for value in variants:
        with pytest.raises(ToolCallError):
            tool_outcome(
                httpx.Response(
                    200,
                    json=value,
                    request=httpx.Request("POST", "http://test/tools/ler_documento"),
                ),
                "ler_documento",
                context,
                expected,
            )
    result = tool_outcome(
        httpx.Response(
            200, json=good, request=httpx.Request("POST", "http://test/tools/ler_documento")
        ),
        "ler_documento",
        context,
        expected,
    )
    assert result == good


def test_storage_failure_is_safe_and_retryable(client, corpus, context, monkeypatch):
    def broken(*args):
        raise SQLAlchemyError("synthetic-private-sql")

    monkeypatch.setattr(CorpusRepository, "read", broken)
    result = read(client, context, corpus[1].document_id)
    assert result.status_code == 503 and result.json()["retryable"]
    assert "synthetic-private" not in result.text

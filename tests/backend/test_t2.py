"""Integrated HTTP and consumer acceptance for literal scoped search."""

from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from agents.interface import ToolCallError, tool_outcome
from pipelines.documents.ingest import chunk_document
from services.backend.corpus import CorpusRepository
from services.backend.storage import chunks, ingest
from tests.backend.test_tool_calls import history


def search(client, context, query="material", limit=5):
    return client.post("/tools/buscar_documentos", json={**context, "query": query, "limit": limit})


def indexed_text(engine, context, text):
    # Synthetic index variation for substring/Unicode and rejected-payload probes.
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(chunks)
                .where(
                    chunks.c.process_id == context["process_id"],
                    chunks.c.corpus_version == context["corpus_version"],
                )
                .order_by(chunks.c.chunk_id)
                .limit(1)
            )
            .mappings()
            .one()
        )
        payload = {**row["payload"], "text": text, "start": 0, "end": len(text)}
        conn.execute(
            update(chunks)
            .where(chunks.c.chunk_id == row["chunk_id"])
            .values(text=text, payload=payload)
        )
    return row["chunk_id"]


def test_scope_precedes_limit_and_order_is_stable(client, context, corpus, engine):
    process, document = corpus
    other = process.model_copy(update={"process_id": "AAA-OTHER-" + uuid4().hex})
    doc = document.model_copy(update={"process_id": other.process_id, "document_id": "AAA-FOREIGN"})
    ingest(engine, other, doc, chunk_document(doc))
    another_version = process.model_copy(update={"corpus_version": "AAA-OTHER"})
    doc = document.model_copy(
        update={"corpus_version": another_version.corpus_version, "document_id": "AAA-CORPUS"}
    )
    ingest(engine, another_version, doc, chunk_document(doc))
    first = search(client, context, limit=1)
    repeated = search(client, context, limit=1)
    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json()
    assert len(first.json()["items"]) == 1
    assert all(
        (c["process_id"], c["corpus_version"]) == (context["process_id"], context["corpus_version"])
        for c in first.json()["items"]
    )


def test_literal_wildcards_escape_and_empty_coverage(client, context, engine):
    chunk_id = indexed_text(engine, context, "Synthetic 100%_ / marcador")
    for term in ("%", "_", "/", "%_", "100%_"):
        result = search(client, context, query=term)
        assert result.status_code == 200
        assert [c["chunk_id"] for c in result.json()["items"]] == [chunk_id]
    result = search(client, context, query="synthetic-missing-term")
    assert result.status_code == 200
    assert result.json()["items"] == []
    assert result.json()["export_completeness"] == "partial"
    assert "não prova" in result.json()["warning"]


@pytest.mark.parametrize(
    "field", ["chunk_id", "document_id", "process_id", "corpus_version", "text"]
)
def test_corrupt_index_payload_returns_safe_error(client, context, engine, field):
    with engine.begin() as conn:
        row = (
            conn.execute(
                select(chunks)
                .where(
                    chunks.c.process_id == context["process_id"],
                    chunks.c.corpus_version == context["corpus_version"],
                )
                .order_by(chunks.c.document_id, chunks.c.chunk_id)
                .limit(1)
            )
            .mappings()
            .one()
        )
        payload = deepcopy(row["payload"])
        payload[field] = "SYNTHETIC-PRIVATE-REJECTED"
        if field == "text":
            payload["end"] = payload["start"] + len(payload["text"])
        conn.execute(
            update(chunks).where(chunks.c.chunk_id == row["chunk_id"]).values(payload=payload)
        )
    # Query the unchanged indexed text; inconsistent payload must not be emitted.
    result = search(client, context, query=row["text"][:10])
    assert result.status_code == 500 and result.json()["code"] == "invalid_response"
    assert not result.json()["retryable"]
    assert "SYNTHETIC-PRIVATE-REJECTED" not in result.text
    assert all(c["http_status"] != 200 for c in history(client, engine, context["run_id"]))


def test_over_limit_and_duplicates_are_refused_before_success(client, context, monkeypatch):
    good = search(client, context).json()
    assert len(good["items"]) >= 2
    monkeypatch.setattr(CorpusRepository, "search", lambda *args: good["items"])
    result = search(client, context, limit=1)
    assert result.status_code == 500 and result.json()["code"] == "invalid_response"
    monkeypatch.setattr(CorpusRepository, "search", lambda *args: good["items"][:1] * 2)
    assert search(client, context).status_code == 500


def test_client_checks_envelope_scope_uniqueness_and_requested_limit(client, context):
    payload = {**context, "query": "material", "limit": 1}
    good = search(client, context, limit=1).json()
    cases = []
    for field in ("run_id", "process_id", "corpus_version", "requirements_version"):
        bad = deepcopy(good)
        bad[field] = str(uuid4()) if field == "run_id" else "OTHER"
        if field in {"process_id", "corpus_version"}:
            for item in bad["items"]:
                item[field] = "OTHER"
        cases.append(bad)
    for field in ("process_id", "corpus_version"):
        bad = deepcopy(good)
        bad["items"][0][field] = "OTHER"
        cases.append(bad)
    cases.append({**good, "items": good["items"] * 2})
    larger = search(client, context, limit=20).json()
    assert len(larger["items"]) > 1
    cases.append(larger)
    for value in cases:
        with pytest.raises(ToolCallError):
            tool_outcome(
                httpx.Response(
                    200,
                    json=value,
                    request=httpx.Request("POST", "http://test/tools/buscar_documentos"),
                ),
                "buscar_documentos",
                context,
                payload,
            )
    parsed = tool_outcome(
        httpx.Response(
            200, json=good, request=httpx.Request("POST", "http://test/tools/buscar_documentos")
        ),
        "buscar_documentos",
        context,
        payload,
    )
    assert parsed == good


def test_search_storage_failure_is_retryable_without_echo(client, context, monkeypatch):
    def broken(*args):
        raise SQLAlchemyError("synthetic-private-query")

    monkeypatch.setattr(CorpusRepository, "search", broken)
    result = search(client, context)
    assert result.status_code == 503 and result.json()["retryable"]
    assert "synthetic-private-query" not in result.text


def test_unicode_behavior_is_measured_without_normalization(client, context, engine):
    chunk_id = indexed_text(engine, context, "AÇÃO Café")
    terms = {
        "AÇÃO": True,
        "Café": True,
        "CAFÉ": engine.dialect.name == "postgresql",
        "ação": engine.dialect.name == "postgresql",
        "cafe": False,
    }
    for term, expected in terms.items():
        result = search(client, context, query=term)
        assert result.status_code == 200
        assert (chunk_id in {c["chunk_id"] for c in result.json()["items"]}) is expected

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pipelines.documents.ingest import chunk_document
from services.backend.storage import ingest, processes


def test_chunk_ids_and_exact_source_offsets(corpus):
    _, document = corpus
    chunks = chunk_document(document, size=80, overlap=10)
    assert chunks == chunk_document(document, size=80, overlap=10)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    pages = {page.number: page.text for page in document.pages}
    for chunk in chunks:
        assert chunk.text == pages[chunk.page][chunk.start : chunk.end]
        assert chunk.document_id == document.document_id
        assert chunk.source == document.source
    for page in document.pages:
        covered = set()
        for chunk in chunks:
            if chunk.page == page.number:
                covered.update(range(chunk.start, chunk.end))
        assert all(i in covered or c.isspace() for i, c in enumerate(page.text))


@pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, -1)])
def test_invalid_chunk_configuration(corpus, size, overlap):
    with pytest.raises(ValueError):
        chunk_document(corpus[1], size, overlap)


def test_idempotent_ingestion_and_immutable_corpus(engine, corpus):
    process, document = corpus
    chunks = chunk_document(document)
    assert ingest(engine, process, document, chunks) == len(chunks)
    assert ingest(engine, process, document, chunks) == 0
    with pytest.raises(ValueError, match="Corpus imutável"):
        ingest(engine, process.model_copy(update={"title": "Outro título"}), document, chunks)
    with pytest.raises(ValueError, match="Chunking diferente"):
        ingest(engine, process, document, chunk_document(document, size=80))


def test_ingestion_rejects_forged_evidence(engine, corpus):
    process, document = corpus
    chunks = chunk_document(document)
    chunks[0] = chunks[0].model_copy(update={"page": 999})
    with pytest.raises(ValueError, match="rastreabilidade"):
        ingest(engine, process, document, chunks)


def test_database_error_rolls_back_the_whole_ingestion(engine, corpus):
    process, document = corpus
    original_chunks = chunk_document(document)
    ingest(engine, process, document, original_chunks)
    other = process.model_copy(update={"process_id": process.process_id + "-rollback"})
    other_doc = document.model_copy(update={"process_id": other.process_id})
    other_chunks = chunk_document(other_doc)
    other_chunks[0] = other_chunks[0].model_copy(
        update={
            "chunk_id": original_chunks[0].chunk_id,
        }
    )
    with pytest.raises(IntegrityError):
        ingest(engine, other, other_doc, other_chunks)
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(processes.c.process_id).where(
                    processes.c.process_id == other.process_id,
                )
            ).first()
            is None
        )

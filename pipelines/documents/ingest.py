"""Ingestão de JSON sintético paginado; não extrai PDF nem executa OCR."""

import hashlib
import json
from pathlib import Path

from contracts.models import Chunk, Document, Process


def load_fixture(directory: Path) -> tuple[Process, Document]:
    process = Process.model_validate_json((directory / "process.json").read_text(encoding="utf-8"))
    raw = (directory / "document.json").read_bytes()
    document = Document.model_validate(
        {**json.loads(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    )
    if (document.process_id, document.corpus_version) != (
        process.process_id,
        process.corpus_version,
    ):
        raise ValueError("Documento e processo devem pertencer ao mesmo corpus.")
    return process, document


def chunk_document(document: Document, size: int = 140, overlap: int = 20) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("Use tamanho positivo e 0 <= sobreposição < tamanho.")
    chunks = []
    for page in document.pages:
        start = 0
        while start < len(page.text):
            end = min(start + size, len(page.text))
            # Retira apenas espaços nas bordas e ajusta os offsets junto com o texto.
            segment = page.text[start:end]
            left = start + len(segment) - len(segment.lstrip())
            right = end - (len(segment) - len(segment.rstrip()))
            if left < right:
                identity = (
                    f"{document.process_id}:{document.document_id}:{document.corpus_version}:"
                    f"{document.sha256}:{page.number}:{left}:{right}"
                )
                chunks.append(
                    Chunk(
                        chunk_id="chunk-" + hashlib.sha256(identity.encode()).hexdigest()[:32],
                        process_id=document.process_id,
                        document_id=document.document_id,
                        corpus_version=document.corpus_version,
                        source=document.source,
                        page=page.number,
                        start=left,
                        end=right,
                        text=page.text[left:right],
                    )
                )
            if end == len(page.text):
                break
            start = end - overlap
    return chunks

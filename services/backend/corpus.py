"""Fronteira de leitura do corpus preparado por Documentos/RAG.

Recebe uma conexão da transação do chamador. Não ingere nem reindexa documentos.
"""

from pydantic import ValidationError
from sqlalchemy import select

from contracts.models import Chunk, Document, InventoryEvidence, Process
from services.backend.errors import fail
from services.backend.storage import chunks, documents, processes


class CorpusRepository:
    def process(self, conn, context):
        row = conn.execute(
            select(processes.c.payload).where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
        ).first()
        if row is None:
            fail(404, "not_found", "Processo/corpus não encontrado.")
        # A present row with JSON null is invalid metadata, not a missing process.
        # Validate before indexing fields so malformed data follows audited ToolFailure.
        try:
            process = Process.model_validate(row[0])
            if (process.process_id, process.corpus_version) != (
                context["process_id"],
                context["corpus_version"],
            ):
                raise ValueError("Stored process identity differs from selected scope")
        except (ValidationError, ValueError):
            fail(500, "invalid_response", "Metadados do processo inconsistentes.")
        if process.requirements_version != context["requirements_version"]:
            fail(409, "version_mismatch", "Versão dos requisitos incompatível.")
        return process.model_dump(mode="json")

    def inventory(self, conn, context):
        items = []
        rows = conn.execute(
            select(documents.c.document_id, documents.c.payload)
            .where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
            )
            .order_by(documents.c.document_id)
        ).mappings()
        for row in rows:
            try:
                doc = Document.model_validate(row["payload"])
                if (doc.document_id, doc.process_id, doc.corpus_version) != (
                    row["document_id"],
                    context["process_id"],
                    context["corpus_version"],
                ):
                    raise ValueError("Inventory scope mismatch")
            except (ValidationError, ValueError):
                fail(500, "invalid_response", "Inventario do processo inconsistente.")
            items.append(
                {
                    "document_id": doc.document_id,
                    "title": doc.title,
                    "source": doc.source,
                    "pages": len(doc.pages),
                    "sha256": doc.sha256,
                }
            )
        return items

    def search(self, conn, context, query, limit):
        # Preserve SQL substring semantics, escaping, ordering and scope before LIMIT.
        rows = conn.execute(
            select(chunks)
            .where(
                chunks.c.process_id == context["process_id"],
                chunks.c.corpus_version == context["corpus_version"],
                chunks.c.text.icontains(query, autoescape=True),
            )
            .order_by(chunks.c.document_id, chunks.c.chunk_id)
            .limit(limit)
        ).mappings()
        items = []
        for row in rows:
            try:
                chunk = Chunk.model_validate(row["payload"])
                if (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.process_id,
                    chunk.corpus_version,
                    chunk.text,
                ) != (
                    row["chunk_id"],
                    row["document_id"],
                    row["process_id"],
                    row["corpus_version"],
                    row["text"],
                ):
                    raise ValueError("Search payload differs from stored index")
            except (ValidationError, ValueError):
                fail(500, "invalid_response", "Resultado de busca inconsistente.")
            items.append(chunk)
        return items

    def read(self, conn, context, document_id, pages=None):
        row = conn.execute(
            select(documents.c.payload).where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
                documents.c.document_id == document_id,
            )
        ).first()
        if row is None:
            fail(404, "not_found", "Documento não encontrado neste processo/corpus.")
        try:
            document = Document.model_validate(row[0])
            if (document.document_id, document.process_id, document.corpus_version) != (
                document_id,
                context["process_id"],
                context["corpus_version"],
            ):
                raise ValueError("Stored document differs from selected scope")
            numbers = [page.number for page in document.pages]
            if numbers != sorted(numbers):
                raise ValueError("Stored document pages are out of order")
        except (ValidationError, ValueError):
            fail(500, "invalid_response", "Documento armazenado inconsistente.")
        if pages is not None and not set(pages) <= set(numbers):
            fail(404, "not_found", "Página não encontrada no documento.")
        result = document.model_dump(mode="json")
        if pages is not None:
            result["pages"] = [page for page in result["pages"] if page["number"] in pages]
        return result

    def validate_sources(self, conn, context, sources):
        for ref in sources:
            if isinstance(ref, InventoryEvidence):
                if (ref.process_id, ref.corpus_version) != (
                    context["process_id"],
                    context["corpus_version"],
                ):
                    fail(422, "validation_error", "Inventário fora do processo/corpus.")
                continue
            row = conn.execute(
                select(chunks.c.payload, chunks.c.text).where(
                    chunks.c.chunk_id == ref.chunk_id,
                    chunks.c.document_id == ref.document_id,
                    chunks.c.process_id == context["process_id"],
                    chunks.c.corpus_version == context["corpus_version"],
                )
            ).first()
            if row is None:
                fail(422, "validation_error", "Referência de evidência inválida.")
            try:
                chunk = Chunk.model_validate(row.payload)
                if (
                    chunk.chunk_id,
                    chunk.document_id,
                    chunk.process_id,
                    chunk.corpus_version,
                    chunk.text,
                ) != (
                    ref.chunk_id,
                    ref.document_id,
                    context["process_id"],
                    context["corpus_version"],
                    row.text,
                ):
                    raise ValueError("Evidence payload differs from stored identity")
            except (ValidationError, ValueError):
                fail(500, "invalid_response", "Evidência armazenada inconsistente.")
            if chunk.page != ref.page:
                fail(422, "validation_error", "Referência de evidência inválida.")

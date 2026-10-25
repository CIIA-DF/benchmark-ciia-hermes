"""Fronteira de leitura do corpus preparado por Documentos/RAG.

Recebe uma conexão da transação do chamador. Não ingere nem reindexa documentos.
"""

from sqlalchemy import select

from contracts.models import InventoryEvidence
from services.backend.errors import fail
from services.backend.storage import chunks, documents, processes


class CorpusRepository:
    def process(self, conn, context):
        row = conn.execute(
            select(processes.c.payload).where(
                processes.c.process_id == context["process_id"],
                processes.c.corpus_version == context["corpus_version"],
            )
        ).scalar_one_or_none()
        if row is None:
            fail(404, "not_found", "Processo/corpus não encontrado.")
        if row["requirements_version"] != context["requirements_version"]:
            fail(409, "version_mismatch", "Versão dos requisitos incompatível.")
        return row

    def inventory(self, conn, context):
        return [
            {
                "document_id": doc["document_id"],
                "title": doc["title"],
                "source": doc["source"],
                "pages": len(doc["pages"]),
                "sha256": doc["sha256"],
            }
            for doc in conn.execute(
                select(documents.c.payload)
                .where(
                    documents.c.process_id == context["process_id"],
                    documents.c.corpus_version == context["corpus_version"],
                )
                .order_by(documents.c.document_id)
            ).scalars()
        ]

    def search(self, conn, context, query, limit):
        return (
            conn.execute(
                select(chunks.c.payload)
                .where(
                    chunks.c.process_id == context["process_id"],
                    chunks.c.corpus_version == context["corpus_version"],
                    chunks.c.text.icontains(query, autoescape=True),
                )
                .order_by(chunks.c.document_id, chunks.c.chunk_id)
                .limit(limit)
            )
            .scalars()
            .all()
        )

    def read(self, conn, context, document_id, pages=None):
        doc = conn.execute(
            select(documents.c.payload).where(
                documents.c.process_id == context["process_id"],
                documents.c.corpus_version == context["corpus_version"],
                documents.c.document_id == document_id,
            )
        ).scalar_one_or_none()
        if doc is None:
            fail(404, "not_found", "Documento não encontrado neste processo/corpus.")
        if pages:
            if not set(pages) <= {p["number"] for p in doc["pages"]}:
                fail(404, "not_found", "Página não encontrada no documento.")
            doc = {**doc, "pages": [p for p in doc["pages"] if p["number"] in pages]}
        return doc

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
                select(chunks.c.payload).where(
                    chunks.c.chunk_id == ref.chunk_id,
                    chunks.c.document_id == ref.document_id,
                    chunks.c.process_id == context["process_id"],
                    chunks.c.corpus_version == context["corpus_version"],
                )
            ).scalar_one_or_none()
            if row is None or row["page"] != ref.page:
                fail(422, "validation_error", "Referência de evidência inválida.")

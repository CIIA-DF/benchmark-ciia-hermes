"""As seis operações de negócio, independentes do transporte FastAPI."""

import time

from sqlalchemy import select

from contracts.models import DocumentResult, ProcessResult, RequirementsResult, SearchResult
from services.backend.errors import fail
from services.backend.schema import requirements


class ToolService:
    def __init__(self, execution):
        self.execution = execution
        self.corpus = execution.corpus

    def call(self, name, actor, query, lease):
        if name in {"registrar_pendencia", "salvar_minuta"}:
            return self.execution.write_artifact(actor, query, lease, name)
        readers = {
            "consultar_processo": self.process,
            "buscar_documentos": self.search,
            "ler_documento": self.read,
            "consultar_requisitos": self.checklist,
        }
        if name not in readers:
            fail(404, "not_found", "Ferramenta fora do catálogo.")
        started = time.perf_counter()
        with self.execution.transaction() as conn:
            row = self.execution.tool_context(conn, actor, query, lease)
            output = readers[name](conn, row["context"], query)
            self.execution.event(
                conn,
                str(query.run_id),
                "tool",
                {
                    "tool": name,
                    "status": "ok",
                    "duration_ms": (time.perf_counter() - started) * 1000,
                },
            )
        return output

    def process(self, conn, context, query):
        return ProcessResult(
            **context,
            process=self.corpus.process(conn, context),
            inventory=self.corpus.inventory(conn, context),
        )

    def search(self, conn, context, query):
        process = self.corpus.process(conn, context)
        return SearchResult(
            **context,
            export_completeness=process["export_completeness"],
            items=self.corpus.search(conn, context, query.query, query.limit),
        )

    def read(self, conn, context, query):
        return DocumentResult(
            **context, document=self.corpus.read(conn, context, query.document_id, query.pages)
        )

    def checklist(self, conn, context, query):
        items = (
            conn.execute(
                select(requirements.c.payload)
                .where(
                    requirements.c.process_id == context["process_id"],
                    requirements.c.corpus_version == context["corpus_version"],
                    requirements.c.requirements_version == context["requirements_version"],
                )
                .order_by(requirements.c.requirement_id)
            )
            .scalars()
            .all()
        )
        if not items:
            fail(404, "not_found", "Checklist desta versão ainda não cadastrado.")
        return RequirementsResult(**context, items=items)

"""As seis operações de negócio, independentes do transporte FastAPI."""

import hashlib
import logging
import re
import time
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from contracts.catalog import TOOLS
from contracts.models import (
    DocumentResult,
    Process,
    ProcessResult,
    Requirement,
    RequirementsResult,
    SearchResult,
)
from services.backend.auth import authenticate
from services.backend.errors import ToolFailure, fail
from services.backend.execution import digest
from services.backend.schema import requirements

logger = logging.getLogger(__name__)
CALL_ID = re.compile(r"[A-Za-z0-9_.:-]{1,120}")


class ToolService:
    def __init__(self, execution):
        self.execution = execution
        self.corpus = execution.corpus

    def attempt(self, name, tool_call_id, args_sha256, physical_attempt_id=None):
        # Toda tentativa tem ID correlacionável; ausente ou inválido, o servidor gera um.
        valid = tool_call_id is not None and CALL_ID.fullmatch(tool_call_id)
        return {
            "physical_attempt_id": physical_attempt_id,
            "tool": name,
            "tool_call_id": tool_call_id if valid else str(uuid4()),
            "args_sha256": args_sha256,
            "started_at": time.time(),
            "clock": time.perf_counter(),
        }

    def call(self, name, actor, query, lease, tool_call_id=None, physical_attempt_id=None):
        if name not in TOOLS:
            fail(404, "not_found", "Ferramenta fora do catálogo.")
        call = self.attempt(
            name, tool_call_id, digest(query.model_dump(mode="json")), physical_attempt_id
        )
        try:
            if tool_call_id is not None and call["tool_call_id"] != tool_call_id:
                fail(422, "validation_error", "Identificador de chamada inválido.")
            with self.execution.transaction() as conn:
                row = self.execution.authorize_tool_context(
                    conn,
                    actor,
                    query,
                    lease,
                    write=name in {"registrar_pendencia", "salvar_minuta"},
                )
                self.execution.reserve_tool_call(conn, row["run_id"], call)
            if name in {"registrar_pendencia", "salvar_minuta"}:
                return self.execution.write_artifact(actor, query, lease, name, call)
            readers = {
                "consultar_processo": self.process,
                "buscar_documentos": self.search,
                "ler_documento": self.read,
                "consultar_requisitos": self.checklist,
            }
            with self.execution.transaction() as conn:
                row = self.execution.tool_context(conn, actor, query, lease, call)
                output = readers[name](conn, row["context"], query)
                output = TOOLS[name].output_model.model_validate(output)
                self.execution.tool_attempt(conn, str(query.run_id), call, 200)
            return output
        except ToolFailure as exc:
            self.failed(actor, lease, call, exc.status, exc.error.code, query.run_id)
            raise
        except SQLAlchemyError:
            self.failed(actor, lease, call, 503, "storage_unavailable", query.run_id)
            raise

    def rejected(self, name, authorization, lease, tool_call_id, body, physical_attempt_id=None):
        """Entrada recusada antes da tool; registrada quando a reserva identifica o run."""
        if name not in TOOLS:
            return
        try:
            actor = authenticate(self.execution.engine, authorization)
        except ToolFailure:
            return
        call = self.attempt(
            name, tool_call_id, hashlib.sha256(body).hexdigest(), physical_attempt_id
        )
        status, code = 422, "validation_error"
        try:
            with self.execution.transaction() as conn:
                row = self.execution.lease_run(conn, actor, lease)
                if row is not None:
                    self.execution.worker_run(conn, actor, row["run_id"], lease)
                    self.execution.reserve_tool_call(conn, row["run_id"], call)
        except ToolFailure as exc:
            status, code = exc.status, exc.error.code
        self.failed(actor, lease, call, status, code)
        if status != 422:
            fail(status, code, "Chamada recusada; consulte o estado da execucao.")

    def failed(self, actor, lease, call, status, code, run_id=None):
        # Transação própria: a auditoria sobrevive ao rollback do efeito recusado.
        try:
            with self.execution.transaction() as conn:
                row = self.execution.lease_run(conn, actor, lease, run_id)
                if row is not None:
                    self.execution.tracking.bind(conn, row["run_id"], call, code)
                    self.execution.tool_attempt(
                        conn,
                        row["run_id"],
                        call,
                        status,
                        code=code,
                        notify=row["status"] == "running",
                    )
        except SQLAlchemyError:
            logger.warning("tool_attempt_not_recorded tool=%s code=%s", call["tool"], code)

    def process(self, conn, context, query):
        try:
            return ProcessResult(
                **context,
                process=self.corpus.process(conn, context),
                inventory=self.corpus.inventory(conn, context),
            )
        except ValidationError:
            fail(500, "invalid_response", "Resposta de processo inconsistente.", context["run_id"])

    def search(self, conn, context, query):
        try:
            process = Process.model_validate(self.corpus.process(conn, context))
            if (process.process_id, process.corpus_version, process.requirements_version) != (
                context["process_id"],
                context["corpus_version"],
                context["requirements_version"],
            ):
                raise ValueError("Search process context mismatch")
            output = SearchResult(
                **context,
                export_completeness=process.export_completeness,
                items=self.corpus.search(conn, context, query.query, query.limit),
            )
            if len(output.items) > query.limit:
                raise ValueError("Search exceeded requested limit")
            return output
        except (ValidationError, ValueError):
            fail(500, "invalid_response", "Resposta de busca inconsistente.", context["run_id"])

    def read(self, conn, context, query):
        try:
            output = DocumentResult(
                **context, document=self.corpus.read(conn, context, query.document_id, query.pages)
            )
            if output.document.document_id != query.document_id:
                raise ValueError("Document differs from requested identity")
            if query.pages is not None and {page.number for page in output.document.pages} != set(
                query.pages
            ):
                raise ValueError("Document pages differ from requested subset")
            return output
        except (ValidationError, ValueError):
            fail(500, "invalid_response", "Resposta de leitura inconsistente.", context["run_id"])

    def checklist(self, conn, context, query):
        try:
            rows = (
                conn.execute(
                    select(requirements.c.requirement_id, requirements.c.payload)
                    .where(
                        requirements.c.process_id == context["process_id"],
                        requirements.c.corpus_version == context["corpus_version"],
                        requirements.c.requirements_version == context["requirements_version"],
                    )
                    .order_by(requirements.c.requirement_id)
                )
                .mappings()
                .all()
            )
            if not rows:
                fail(404, "not_found", "Checklist desta versão ainda não cadastrado.")
            items = []
            for row in rows:
                item = Requirement.model_validate(row["payload"])
                if item.requirement_id != row["requirement_id"]:
                    raise ValueError("Checklist payload differs from stored identity")
                items.append(item)
            return RequirementsResult(**context, items=items)
        except (ValidationError, ValueError):
            fail(500, "invalid_response", "Checklist armazenado inconsistente.", context["run_id"])

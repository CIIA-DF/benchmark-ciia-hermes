"""Executor determinístico de demonstração. Não executa inferência nem avalia conteúdo."""

import asyncio
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from contracts.execution import AgentEvent, AgentResult
from contracts.models import ExperimentRun


class SimulationAdapter:
    async def stream(self, execution, tools):
        started = datetime.now(UTC)
        yield AgentEvent(event_id=uuid4(), kind="status", text="Consultando documentos fictícios")
        process = await tools.call("consultar_processo", {})
        await tools.call("consultar_requisitos", {})
        # Termo da fixture é intencional: este executor demonstra o protocolo, não faz RAG real.
        found = await tools.call("buscar_documentos", {"query": "material"})
        count = sum(m["role"] == "user" for m in execution.history)
        answer = (
            f"Demonstração simulada — nenhuma LLM foi chamada.\n\n"
            f"Esta é a pergunta {count} da conversa: {execution.task}\n\n"
            f"Processo: {process['process']['title']}. "
            f"Cobertura: {process['process']['export_completeness']}.\n\n"
        )
        sources = []
        if found["items"]:
            item = found["items"][0]
            await tools.call(
                "ler_documento", {"document_id": item["document_id"], "pages": [item["page"]]}
            )
            answer += f"Trecho fictício recuperado: {item['text']}\n\n"
            sources = [{k: item[k] for k in ("document_id", "chunk_id", "page")}]
        answer += found["warning"]
        for offset in range(0, len(answer), 40):
            yield AgentEvent(event_id=uuid4(), kind="text_delta", text=answer[offset : offset + 40])
            await asyncio.sleep(0.04)
        report = None
        if execution.kind == "benchmark":
            report = ExperimentRun(
                **execution.context,
                **execution.task_metadata,
                executor="simulation",
                code_commit="simulation-only",
                harness_version="0.2",
                adapter_version="0.2",
                model="not-called",
                endpoint_id="none",
                prompt_sha256=hashlib.sha256(execution.task.encode()).hexdigest(),
                parameters={},
                started_at=started,
                latency_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
                tool_calls=[],
                agent_declared_success=False,
                persisted_artifact_ids=[],
                verified_success=None,
                evaluator=None,
            )
        yield AgentResult(status="succeeded", answer=answer, sources=sources, experiment=report)

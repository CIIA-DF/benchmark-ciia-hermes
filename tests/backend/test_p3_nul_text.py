"""P3: U+0000 recusado com 422 em textos livres, como em SearchInput.query (F2).

Achado de 30/10/2026: PostgreSQL não armazena U+0000 em texto; o valor passava pela validação
e só falhava no banco (503/500 no PostgreSQL, aceito no SQLite).
"""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from contracts.execution import AgentEvent, AgentResult, HistoryMessage, MessageInput, RunInput
from contracts.models import ToolContext
from tests.backend.test_compat import queue_and_claim, report
from tests.backend.test_tool_calls import write_body


@pytest.mark.parametrize(
    "build",
    [
        lambda: AgentResult(status="succeeded", answer="resposta\x00"),
        lambda: AgentEvent(event_id=uuid4(), kind="text_delta", text="\x00"),
        lambda: MessageInput(content="olá\x00", idempotency_key="p3"),
        lambda: RunInput(
            process_id="P",
            corpus_version="c",
            requirements_version="r",
            task="tarefa\x00",
            task_id="DEV-001",
            idempotency_key="p3",
        ),
    ],
)
def test_contract_texts_reject_nul(build):
    with pytest.raises(ValidationError):
        build()


def p7_report(**changes):
    context = ToolContext(
        run_id=uuid4(), process_id="P", corpus_version="c", requirements_version="r"
    )
    return report(context, "tarefa", **changes)


@pytest.mark.parametrize(
    "build",
    [
        lambda: p7_report(parameters={"nota": "x\x00"}),
        lambda: p7_report(parameters={"no\x00me": "x"}),
        lambda: p7_report(evaluator="avaliador\x00"),
        lambda: TypeAdapter(HistoryMessage).validate_python(
            {"role": "assistant", "content": "resposta\x00"}
        ),
    ],
)
def test_p7_remaining_free_texts_reject_nul(build):
    with pytest.raises(ValidationError):
        build()


def test_p7_empty_or_spaced_texts_remain_valid():
    assert p7_report(parameters={"nota": ""}).parameters == {"nota": ""}
    history = {"role": "assistant", "content": ""}
    assert TypeAdapter(HistoryMessage).validate_python(history) == history


def test_p7_experiment_route_rejects_nul_parameter_with_422(client, corpus):
    execution = queue_and_claim(client, corpus, "benchmark")
    body = report(ToolContext.model_validate(execution.context), execution.task).model_dump(
        mode="json"
    )
    body["parameters"] = {"n": "x\x00"}
    headers = {**client.worker_headers, "X-Run-Token": execution.run_token}
    response = client.post("/experiments", json=body, headers=headers)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


def test_empty_answer_without_nul_is_still_valid():
    assert AgentResult(status="failed", error_code="adapter_error").answer == ""


def test_write_tool_rejects_nul_content_with_422(client, context, corpus):
    body = write_body(context, corpus)
    body["content"] = "minuta\x00"
    response = client.post("/tools/salvar_minuta", json=body, headers={"X-Tool-Call-Id": "p3"})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"
    assert "\\u0000" not in response.text


def test_run_creation_rejects_nul_task(client, context):
    response = client.post(
        "/runs",
        headers=client.operator_headers,
        json={
            "process_id": context["process_id"],
            "corpus_version": context["corpus_version"],
            "requirements_version": context["requirements_version"],
            "task": "tarefa\x00",
            "task_id": "DEV-001",
            "idempotency_key": str(uuid4()),
        },
    )
    assert response.status_code == 422, response.text

"""P3: U+0000 recusado com 422 em textos livres, como em SearchInput.query (F2).

Achado de 30/10/2026: PostgreSQL não armazena U+0000 em texto; o valor passava pela validação
e só falhava no banco (503/500 no PostgreSQL, aceito no SQLite).
"""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts.execution import AgentEvent, AgentResult, MessageInput, RunInput
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

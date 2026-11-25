"""P2: o ID lógico gerado pelo servidor volta ao cliente em X-Tool-Call-Id.

Achado de 30/10/2026: sem o cabeçalho (opcional no OpenAPI), o servidor gerava um ID que o
cliente nunca recebia, e o /result recusava qualquer declaração da chamada.
"""

from services.backend.tools import CALL_ID
from tests.backend.test_a2 import call, finish, result


def test_generated_call_id_is_returned_and_can_be_declared(client, context):
    response = client.post("/tools/consultar_processo", json=context)
    assert response.status_code == 200, response.text
    generated = response.headers.get("x-tool-call-id")
    assert generated and CALL_ID.fullmatch(generated)
    stored = finish(client, context, result(context, [call(generated)]))
    assert stored.status_code == 200, stored.text


def test_client_call_id_is_echoed_on_success_and_error(client, context):
    ok = client.post("/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "p2-ok"})
    assert ok.status_code == 200 and ok.headers["x-tool-call-id"] == "p2-ok"
    missing = client.post(
        "/tools/ler_documento",
        json={**context, "document_id": "DOC-P2-INEXISTENTE"},
        headers={"X-Tool-Call-Id": "p2-missing"},
    )
    assert missing.status_code == 404 and missing.headers["x-tool-call-id"] == "p2-missing"


def test_generated_ids_differ_between_requests(client, context):
    ids = {
        client.post("/tools/consultar_processo", json=context).headers["x-tool-call-id"]
        for _ in range(2)
    }
    assert len(ids) == 2


def test_invalid_client_call_id_is_rejected_without_echo(client, context):
    response = client.post(
        "/tools/consultar_processo", json=context, headers={"X-Tool-Call-Id": "invalido com espaco"}
    )
    assert response.status_code == 422, response.text
    assert "x-tool-call-id" not in response.headers

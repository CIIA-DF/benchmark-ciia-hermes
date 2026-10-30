"""A12: process listing validates identity as well as public structure."""

import pytest
from sqlalchemy import delete, insert, update

from contracts.models import Process
from services.backend.auth import authenticate
from services.backend.schema import permissions
from services.backend.storage import processes


@pytest.mark.parametrize(
    "case", ["foreign_id", "foreign_corpus", "missing_version", "wrong_type", "null"]
)
def test_corrupted_authorized_process_has_safe_invalid_response(client, corpus, engine, case):
    process, _ = corpus
    payload = process.model_dump(mode="json")
    if case == "null":
        payload = None
    elif case == "missing_version":
        del payload["requirements_version"]
    else:
        field, value = {
            "foreign_id": ("process_id", "PRIVATE-A12-foreign"),
            "foreign_corpus": ("corpus_version", "PRIVATE-A12-foreign"),
            "wrong_type": ("title", 123),
        }[case]
        payload[field] = value
    with engine.begin() as conn:
        conn.execute(
            update(processes)
            .where(
                processes.c.process_id == process.process_id,
                processes.c.corpus_version == process.corpus_version,
            )
            .values(payload=payload)
        )
    response = client.get("/processos", headers=client.operator_headers)
    assert response.status_code == 500 and response.json()["code"] == "invalid_response"
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A12" not in response.text


def test_process_listing_preserves_scope_typed_output_and_valid_empty(client, corpus, engine):
    with engine.begin() as conn:
        conn.execute(
            insert(processes).values(
                process_id="PRIVATE-A12-ungranted", corpus_version="PRIVATE-A12-other", payload=None
            )
        )
    response = client.get("/processos", headers=client.operator_headers)
    assert response.status_code == 200
    assert [Process.model_validate(item) for item in response.json()] == [corpus[0]]
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE-A12" not in response.text
    profile = authenticate(engine, client.operator_headers["Authorization"])
    with engine.begin() as conn:
        conn.execute(
            delete(permissions).where(permissions.c.principal_id == profile["principal_id"])
        )
    empty = client.get("/processos", headers=client.operator_headers)
    assert empty.status_code == 200 and empty.json() == []
    assert client.get("/processos").status_code == 403
    assert client.get("/processos", headers={"Authorization": ""}).status_code == 401

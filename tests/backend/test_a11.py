"""A11: health proves an actual SQL round-trip and no worker/LLM claim."""

from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from contracts.execution import HealthResponse
from contracts.models import ToolError


def test_health_executes_sql_even_without_enabled_workers(client, engine):
    client.app.state.execution.enabled = set()
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/health", headers={"Authorization": ""})
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200
    assert HealthResponse.model_validate(response.json()) == HealthResponse()
    assert statements == ["SELECT 1"]
    assert not ({"worker_recent", "model", "executor", "llm"} & response.json().keys())


def test_health_query_failure_is_safe_503_and_recovers(client, engine, caplog):
    def unavailable(conn, cursor, statement, parameters, context, executemany):
        if statement == "SELECT 1":
            raise SQLAlchemyError("PRIVATE-A11 connection details")

    event.listen(engine, "before_cursor_execute", unavailable)
    try:
        response = client.get("/health")
    finally:
        event.remove(engine, "before_cursor_execute", unavailable)
    assert response.status_code == 503
    error = ToolError.model_validate(response.json())
    assert error.code == "storage_unavailable" and error.retryable is True
    assert "PRIVATE-A11" not in response.text + caplog.text
    assert client.get("/health").status_code == 200


def test_health_connection_acquisition_failure_is_503(client, engine, monkeypatch):
    def unavailable():
        raise SQLAlchemyError("PRIVATE-A11 pool unavailable")

    monkeypatch.setattr(engine, "connect", unavailable)
    response = client.get("/health")
    assert response.status_code == 503 and response.json()["code"] == "storage_unavailable"
    assert "PRIVATE-A11" not in response.text

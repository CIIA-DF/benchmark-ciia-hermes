"""GET /ready: schema na revisão head, separado de /health."""

from sqlalchemy import text


def test_ready_reports_head_revision(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "schema_revision": "0010"}


def test_ready_fails_while_schema_is_behind_but_health_stays_up(client, engine):
    with engine.begin() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        conn.execute(text("UPDATE alembic_version SET version_num = '0009'"))
    try:
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["code"] == "storage_unavailable"
        assert response.json()["retryable"] is True
        assert client.get("/health").status_code == 200
    finally:
        # Com TEST_DATABASE_URL (PostgreSQL compartilhado), a revisão falsa não pode vazar
        # para os testes seguintes.
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": head})

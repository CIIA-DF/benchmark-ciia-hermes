# Integração mínima

`uv run --locked python -m scripts.dev test-integration` valida ingestão, commit, reconexão, consulta, busca, origem e idempotência. Usa a aplicação FastAPI real por ASGI com dados fictícios.

Padrão SQLite temporário; na CI, TEST_DATABASE_URL seleciona PostgreSQL 17 dedicado. A demo --url acrescenta teste HTTP com servidor real. Execução local não comprova comportamento no GitHub ou na VPS.

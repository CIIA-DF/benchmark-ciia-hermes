# Backend compartilhado

FastAPI com SQLAlchemy; três leituras implementadas, três contratos com HTTP 501. [Aplicação](app.py), [persistência](storage.py), [catálogo](../../contracts/README.md).

```sh
uv run --locked python -m scripts.dev demo
uv run --locked python -m scripts.dev serve
```

No navegador: http://127.0.0.1:8000/docs. Teste: `uv run --locked python -m scripts.dev test-backend` e `test-integration`.

DATABASE_URL seleciona PostgreSQL ou SQLite. Sem variável, usa data/demo.db. Schema criado inicialmente no startup/seed, sem migrações automáticas. Consultas exigem run_id, processo e versões. Busca tem filtro antes do limite e curingas escapados.

API local sem autenticação, para dados fictícios. Autorização, requisitos e escritas ainda precisam ser implementados. [Guia da equipe](../../docs/teams/backend.md).

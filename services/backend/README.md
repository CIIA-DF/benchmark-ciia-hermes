# Backend compartilhado

FastAPI com SQLAlchemy; três leituras implementadas, três contratos com HTTP 501. [Aplicação](app.py), [persistência](storage.py), [catálogo](../../contracts/README.md).

```sh
uv run --locked python -m scripts.dev demo
uv run --locked python -m scripts.dev serve
```

No navegador: http://127.0.0.1:8000/docs. Teste: `uv run --locked python -m scripts.dev test-backend` e `test-integration`.

DATABASE_URL seleciona PostgreSQL ou SQLite. Sem variável, usa data/demo.db. Schema criado inicialmente no startup/seed, sem migrações automáticas. Consultas exigem run_id, processo e versões. Busca tem filtro antes do limite e curingas escapados.

`POST /experiments` salva `ExperimentRun` idempotente; `GET /experiments/{run_id}` relê o estado atual; `PUT /experiments/{run_id}` exige revisão sequencial em `parameters.revision` e preserva histórico; `GET /experiments/{run_id}/revisions` lê as versões. O schema aditivo está em [migration 001](migrations/001_experiment_runs.sql), com [rollback](migrations/001_experiment_runs.down.sql), e é criado pelo `initialize()` em bancos locais.

API local sem autenticação, somente para dados sintéticos em loopback/rede interna. Esse registro é telemetria experimental, não escrita de pendência/minuta no SEI; autorização e ferramentas de negócio continuam pendentes. [Guia da equipe](../../docs/03-equipes/backend.md).

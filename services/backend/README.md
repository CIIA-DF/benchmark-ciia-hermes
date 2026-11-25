# Backend compartilhado

[Referência vigente das APIs](../../docs/02-arquitetura/backend-api-atual.md) · [Estado atual e migrações](../../docs/04-operacoes/backend-estado-atual.md).

As seis tools estão implementadas com FastAPI, Pydantic e SQLAlchemy. Leituras
preservam processo/corpus e fontes; escritas validam evidências e requisitos,
usam transação/idempotência e devolvem recibos confirmados.

[PRD](../../docs/02-arquitetura/backend-prd.md) ·
[TDD](../../docs/02-arquitetura/backend-tdd.md) ·
[Contratos](../../contracts/README.md) ·
[Executar localmente](../../docs/04-operacoes/chat.md)

A lógica está em tools.py, a fronteira RAG em corpus.py e a execução/memória em
execution.py. app.py fornece transporte HTTP. A ingestão e a qualidade da
recuperação continuam com Documentos/RAG; busca atual é literal, não vetorial.

O banco distingue o `run` da chamada lógica identificada por `tool_call_id`:
essa chamada vincula ferramenta e argumentos antes do efeito. Uma chamada pode
ter várias requisições físicas registradas com suas fases; resposta preparada
não comprova entrega ao cliente. Escritas geram artefatos identificados também
por chave de idempotência. `tool_calls` preserva o histórico de etapas legado;
`physical_tool_attempts` e `physical_tool_phases` descrevem requisições físicas.
Alterações nas tabelas de `schema.py` exigem revisão Alembic.

Migrações Alembic precedem o uso do banco. Tools exigem worker autenticado e
reserva ativa; operador consulta conversas e artefatos. O participante do chat
não precisa de login no piloto local, mas seu marcador não é autorização.

```powershell
uv sync --locked
uv run --locked python -m scripts.dev demo
uv run --locked python -m scripts.dev test-backend
uv run --locked python -m scripts.dev test-integration
uv run --locked python -m scripts.dev check
```

SQLite é prévia. PostgreSQL é necessário para comprovar concorrência operacional.
O simulador não é um agente real; integrações dependem das equipes.

# A11 — Saúde da API e consulta ao banco

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A11 do plano](../02-arquitetura/backend-plano-blocos.md).

GET /health já executava SELECT 1 no banco configurado. A regra foi preservada; app/OpenAPI agora explicitam seu alcance.
200 confirma aquisição de conexão e essa consulta. Não comprova schema completo, processamento de fila, worker, modelo ou inferência.
O endpoint continua público e HealthResponse mantém os campos anteriores. Não houve migração nem mudança nos clientes.
Falha ao adquirir conexão ou executar SQL retorna 503 storage_unavailable, retryable true, sem detalhes internos.
O resultado não é mantido em cache de aplicação: após recuperação da consulta, a próxima chamada volta a 200.

```sh
uv run --locked python -m pytest tests/backend/test_a11.py tests/backend/test_openapi.py --durations=5
```

**5 aprovados em SQLite em 55,42 segundos**, log tmp/a11-directed.log.
Três próprios verificam a instrução SQL real com nenhum executor habilitado, falha da consulta seguida de recuperação,
e falha de aquisição da conexão. Dois próximos verificam exportação e envelopes OpenAPI.
Dados e falhas exclusivamente sintéticos. Nenhuma asserção funcional falhou; aviso Starlette/HTTPX existente permanece.
Lint/formato, OpenAPI, links/invariantes e whitespace conferidos.

Aceite A11 comprovado localmente. Suíte completa reservada ao fechamento A.
PostgreSQL, infraestrutura/rede, worker/LLM reais e revisão manual CTO/Astra não homologados.
Sem commit, push, PR, deploy ou revisão automática.

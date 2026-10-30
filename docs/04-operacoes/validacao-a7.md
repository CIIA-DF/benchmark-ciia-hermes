# A7 — Heartbeat autorizado e presença observada

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A7 do plano](../02-arquitetura/backend-plano-blocos.md). Sem publicação ou revisão automática.

## Implementação e workflow

POST /runs/{id}/heartbeat trava o run e valida titular, lease, estado, prazo e grants atuais.
Reutiliza observe_worker do A6 para reler e travar o perfil atual: papel worker, executor do run e hash da credencial precisam corresponder.
Após adquirir a trava do perfil, revalida grants do worker e do proprietário. Grava presença heartbeat e lease na mesma transação.
Falha posterior desfaz ambas as atualizações. Heartbeat não altera cursor, eventos, started_at ou orçamento máximo de execução.
Não renova lease inválido ou vencido, nem ressuscita execução finalizada/expirada.

## Respostas e compatibilidade

200 mantém HeartbeatResponse com status running e no-store. 401 preserva autenticação; 403 cobre lease/titular e perfil incompatível.
409 cobre execução terminal ou prazo vencido; 422 mantém validação de UUID; 503 cobre armazenamento com envelope seguro.
Não houve mudança nos campos, cabeçalhos ou frequência exigida dos clientes. Presença não comprova inferência ou conexão de LLM.
Não houve nova migração: usa worker_presence do A6. App e OpenAPI descrevem renovação atômica e recusas.

## Depuração e evidências

```sh
uv run --locked python -m pytest tests/backend/test_a7.py tests/backend/test_execution.py::test_cross_run_lease_and_evidence_are_rejected tests/backend/test_execution.py::test_lease_expiration_preserves_partial_and_excludes_failed_memory --durations=5
```

Seleção final: **10 aprovados em SQLite, em 32,91 segundos**, log tmp/a7-directed.log.
Oito próprios cobrem renovação conjunta, três alterações de identidade entre autenticação e efeito, lease inválido,
rollback por falha SQL e disputas com expiração/finalização entre duas aplicações. Duas regressões próximas verificam isolamento e timeout/memória.
Primeira rodada: sete passaram e três asserções falharam por procurar code dentro de error; o contrato existente expõe code no nível raiz.
A asserção foi corrigida, sem alterar o envelope público. A seleção inteira foi repetida e aprovada; repetições não contam como testes distintos.
Aviso existente Starlette/HTTPX permanece.

Aceite A7 comprovado localmente. Lint, formato, OpenAPI e links verificados nesta entrega.
Suíte completa reservada ao fechamento A. PostgreSQL, concorrência entre processos, LLMs reais e revisão manual CTO/Astra pendentes.
Sem commit, push, PR ou deploy. Os testes usam bancos sintéticos temporários no C:, sem depender do checkout antigo no D:.

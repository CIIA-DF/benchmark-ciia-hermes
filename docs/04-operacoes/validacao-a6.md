# A6 — Claim e presença durável do worker

Data: 30/10/2026. Worktree oficial em C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A6 do plano](../02-arquitetura/backend-plano-blocos.md). Trabalho local, sem publicação.

## Implementação e workflow

POST /runs/claim autentica o worker e confere seu executor. A manutenção A5 retira fila vencida.
Na transação de claim, o perfil atual é relido sob trava: papel, executor e hash da credencial precisam corresponder.
Só então é gravada a presença e selecionada uma candidata autorizada, sob trava exclusiva.
A candidata é revalidada quanto ao prazo antes de receber worker e lease. Apenas um claim a recebe.
Sem candidata autorizada, retorna 204 sem corpo, preservando a presença do polling válido.

A migração aditiva 0007 cria worker_presence, com principal_id, executor, observed_at e source.
Existe uma linha por principal, atualizada a cada polling válido. Não há token, lease ou conteúdo de usuário nessa tabela.
Migração não cria presença fictícia a partir de histórico. Downgrade remove apenas a tabela nova.
Os testes migram bancos sintéticos isolados; não houve migração de banco operacional.
O registro usa trava do principal antes de inserir/atualizar, sem upsert específico de um banco.
Falha transacional desfaz presença e claim em conjunto. Presença comprova uma chamada válida, não inferência ou saúde de LLM.

## Respostas e consumidores

200 mantém ClaimedRun e run_token; 204 mantém fila sem trabalho; 401/403 recusam credencial ou perfil/executor incompatível.
422 preserva validação da entrada e 503 preserva falha de armazenamento/configuração.
As respostas privadas mantêm no-store. Não houve novo campo público, mudança de cliente ou exposição da tabela.
Presença será consumida no A10; heartbeat será tratado separadamente em A7.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/backend/test_a6.py tests/backend/test_a5.py::test_claim_rechecks_deadline_after_initial_expiry_pass tests/backend/test_execution.py::test_targeted_claim_does_not_take_another_queued_run --durations=5
```

6 testes aprovados em SQLite, em 34,91 segundos; log tmp/a6-directed.log.
Quatro testes próprios cobrem polling vazio repetido sem segredo, identidade inválida ou revogada entre autenticação e efeito,
claim concorrente exclusivo/direcionado e downgrade/upgrade sem perda de runs ou backfill de presença.
Duas regressões próximas cobrem prazo atravessado durante claim e seleção por ID sem consumir outra execução.
Aviso existente Starlette/HTTPX permanece.

Aceite local A6 comprovado pela seleção dirigida. PostgreSQL, concorrência entre processos e runtimes reais não homologados.
Suíte completa reservada ao fechamento A. Sem commit, push, PR, deploy ou revisão automática CTO/Astra.

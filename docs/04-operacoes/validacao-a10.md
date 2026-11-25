# A10 — Configuração e presença são sinais distintos

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A10 do plano](../02-arquitetura/backend-plano-blocos.md). Sem publicação.

## Contrato e workflow

GET /capabilities preserva available: continua indicando configuração habilitada em ENABLED_EXECUTORS, não conexão comprovada.
Acrescenta enabled (mesmo valor), worker_recent, last_seen_at, model e configuration_known a cada executor.
Mantém name, simulation, can_write e profile. As saídas são validadas pelo ExecutorCapability atualizado, com booleanos estritos e timestamp float/null.

A consulta agrega a última presença A6/A7 de workers cujo perfil atual é worker e cujo executor atual corresponde ao observado.
Exige concessão de processo/corpus em comum com o operador; não expõe identidade individual, token ou escopo de terceiros.
worker_recent é true até exatamente 60 segundos da observação, inclusive; depois false, preservando last_seen_at histórico autorizado.
Observação futura é ignorada. Ausência de registro autorizado resulta em worker_recent false e last_seen_at null.
O instante é do servidor que recebeu polling/heartbeat, não prova que o processo continua conectado ou que inferência funciona.
Rotação de credencial não apaga uma observação histórica do mesmo principal; papel, executor e grants atuais continuam filtrando sua exposição.

Configuração desabilitada pode coexistir com presença ainda recente; cada sinal mantém seu significado.
model é null e configuration_known é false porque a API não recebe atestado do modelo/configuração do worker remoto.
Não se infere isso de LLM_MODEL ou outras variáveis do processo da API. O simulador não é apresentado como inferência real.
O portal tipa os novos campos e apresenta desabilitado, worker recente ou sem presença recente; não usa ausência de presença como prova de desconexão.
Durante carregamento, o fallback identifica que ainda aguarda estado. Não houve mudança do fluxo de envio.

## Respostas e evidências

200 mantém resposta privada no-store; 401/403 preservam autenticação/papel e 503 mantém falha de banco segura.
Nenhuma migração nova. A consulta consome worker_presence e permissões existentes.
Consumidores com schemas fechados precisam incorporar os campos aditivos; available não deve ser reinterpretado.

```sh
uv run --locked python -m pytest tests/backend/test_a10.py tests/backend/test_a6.py::test_empty_poll_updates_one_durable_presence_without_exposing_secret tests/backend/test_a7.py::test_heartbeat_refreshes_lease_and_presence_together tests/backend/test_openapi.py --durations=5
```

**13 aprovados em SQLite em 67,77 segundos**, log tmp/a10-directed.log.
Nove próprios cobrem habilitado sem worker/modelo conhecido, fronteiras 59,999/60/60,001 segundos,
configuração desabilitada com presença, revogação de escopo/papel/executor, autenticação e relógio futuro.
Quatro regressões próximas cobrem produtores de presença A6/A7 e OpenAPI. Nenhuma falha funcional na seleção.
Aviso Starlette/HTTPX existente permanece.

Lint/formato, OpenAPI, links/invariantes e whitespace conferidos.
Portal: lint dirigido de app/chat/page.tsx e TypeScript sem emissão aprovados. portal/AGENTS.md lido; guias Next não existem na instalação.
Alteração usa tipos e elementos/formato já existentes, sem API nova de framework ou dependências.
Aceite A10 comprovado localmente. Suíte completa reservada ao fechamento A.
PostgreSQL, relógios entre hosts, worker/LLM reais, inspeção visual/build e revisão manual CTO/Astra pendentes.
Sem commit, push, PR, deploy ou revisão automática.

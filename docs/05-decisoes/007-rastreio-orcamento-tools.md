# ADR 007 — rastreio de tentativas e orçamento comum das tools (contrato v0.3)

Data: 25/10/2026. Estado: implementado localmente na `team/backend`; proposta às equipes
até 28/10/2026, ainda sem aprovação de Hermes, LangGraph e Metodologia.
Responsáveis pela revisão: Backend, Hermes, LangGraph e Metodologia.

## Contexto

A auditoria de 24/10 (A03) mostrou que só leituras bem-sucedidas e escritas novas geravam
registro. Erros, replays e entradas recusadas desapareciam, e não havia ID para correlacionar
as chamadas declaradas pelo adaptador com o que o servidor executou. O guia pede logs
correlacionados (pp. 11, 15, 18), novas tentativas limitadas e registradas (p. 14) e limites
comuns de chamadas (pp. 13, 17). O protocolo exige orçamentos comparáveis entre executores.

## Decisão

- **Uma instrumentação**: `ToolService.call` é o único ponto. `ExecutionService` grava cada
  tentativa na tabela `tool_calls` (migração 0004) e oferece a leitura única
  `tool_call_history`. O orçamento, a validação do benchmark e a exportação consomem esse
  mesmo histórico.
- **Correlação**: cabeçalho opcional `X-Tool-Call-Id`, gerado pelo cliente comum por chamada
  lógica, repetido nas novas tentativas e igual a `ExperimentRun.tool_calls[].tool_call_id`.
- **Auditoria que sobrevive à falha**: sucesso na transação do efeito; falha depois do
  rollback, em transação própria. Só o titular da reserva escreve no histórico do run.
  Argumentos ficam só como SHA-256.
- **Orçamento comum**: `RUN_MAX_TOOL_CALLS` conta `tool_call_id` distintos por run, sob a
  trava do run. Excedido, responde 409 `budget_exceeded`. O padrão 0 mantém o comportamento
  anterior até a Metodologia definir o valor.
- **Novas tentativas no cliente comum**: até 3 tentativas para `retryable: true` ou erro de
  transporte, com o mesmo corpo e ID, para que Hermes e LangGraph se comportem igual.
- `contract_version` passa a `0.3`. Todas as adições são opcionais para quem consome.

## Consequências e pendências

- Adaptadores que usam `AsyncToolClient` recebem correlação, novas tentativas e
  `tools.calls` sem mudar código. Quem montar requisições próprias deve enviar o cabeçalho.
- `budget_exceeded` é um código novo em `ToolError`. Clientes que validam o enum precisam da
  versão atual de `contracts/`.
- Pendente com a Metodologia: valor do orçamento, se falhas e recusas contam como chamada
  lógica (hoje contam), e campos da exportação.
- Pendente com Hermes e LangGraph: aceite do cabeçalho e da política de novas tentativas
  centralizada no cliente comum.
- A validação de `ExperimentRun.tool_calls` contra o histórico (A05) e a exportação ficam
  no bloco 3 do [plano](../02-arquitetura/backend-plano-lacunas.md).

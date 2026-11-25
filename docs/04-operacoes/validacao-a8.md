# A8 — Teto durável de eventos por execução

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A8 do plano](../02-arquitetura/backend-plano-blocos.md). Alterações locais para revisão manual.

## Regra, workflow e atomicidade

MAX_EVENTS_PER_RUN vale 20.000. O contador persistido event_sequence, protegido pela trava do run, abrange criação,
claim, status/text_delta enviados pelo worker, notificações de ferramentas e done. A última vaga é exclusiva do terminal.
Até a sequência 19.999, eventos novos podem ser aceitos. Uma tentativa adicional não terminal recebe 429 resource_limit,
retryable false, e o servidor encerra o run como failed, com result.error_code event_limit e done na sequência 20.000.
O operador deve consultar o snapshot; repetir eventos não reabre a execução.

Replay idêntico de event_id já aceito retorna a sequência anterior sem gastar vaga enquanto o run estiver ativo.
Conteúdo diferente mantém 409 idempotency_conflict. Execução terminal mantém recusa 409, inclusive para replay de evento.
Entrada AgentEvent continua fechada: somente status/text_delta; o worker não pode enviar done nem forjar a causa event_limit em AgentResult.
Finalização normal ou expiração ainda pode usar a última vaga. Não há scheduler novo nem limpeza de histórico.

Se uma operação alcança o teto ao emitir evento, sua transação é desfeita antes do encerramento.
Isso inclui efeitos novos de artefatos e mensagem de resposta; reservas lógicas já confirmadas permanecem.
Na mesma conexão, outra transação relê/trava o run e grava estado, resultado e done juntos.
Se outra finalização venceu a disputa, seu desfecho é preservado. Não há segundo done ou sobrescrita terminal.
Reutilizar a conexão evita dependência de uma vaga extra no pool durante recuperação.
Falha SQL nessa transação retorna 503 storage_unavailable seguro, sem estado terminal parcial; uma tentativa seguinte pode concluir o encerramento.

Notificação de tool usa a mesma quota, sem caminho de bypass. Uma escrita cujo evento excederia o teto sofre rollback;
o ledger e a tentativa física registram a recusa. Uma falha de negócio junto ao teto conserva seu código original e ledger,
substituindo apenas a notificação não terminal pelo done reservado. Tentativas posteriores não geram eventos de erro em ciclo.
Histórico, parciais e artefatos anteriormente confirmados permanecem consultáveis.

O teto aplica-se prospectivamente. Histórico legado que já ultrapassou a reserva não é apagado nem renumerado;
se ainda ativo, seu encerramento acrescenta um único done além do histórico anterior. Não se afirma total retroativo de 20.000 nesses registros.
Nenhuma migração ou reconstrução de contadores históricos foi executada nesta etapa.

## Contratos e consumidores

StoredResult acrescenta event_limit; AgentResult do worker mantém seu enum anterior. EventReceipt e sequência permanecem iguais.
POST de eventos, claim e as seis tools documentam 429. A descrição comum orienta consultar retryable e snapshot, sem retry automático.
Portal recebeu a mensagem da causa no mapa existente, sem mudança de layout. Consumidores com enum fechado precisam incorporar a nova causa.
Semântica do 429 da fila continua temporária/retryable true; limite de eventos é terminal/retryable false.
GET retorna 200 ao ler o resultado failed; SSE transmite done com a causa e termina. Isso não significa sucesso da tarefa.

## Depuração e evidências

```sh
uv run --locked python -m pytest tests/backend/test_a8.py tests/backend/test_execution.py::test_event_replay_sse_cursor_and_result_consistency tests/backend/test_openapi.py --durations=5
```

**11 testes aprovados em SQLite em 78,36 segundos**, log tmp/a8-directed.log.
Oito próprios incluem a fronteira real de 20.000 linhas contíguas, replay/conflito, parciais e SSE,
rollback de uma segunda minuta preservando o primeiro artefato, ledger de falha de negócio,
duas disputas terminais, erro SQL no done, recusa de causa/tipo forjados e recuperação com pool de uma conexão.
Três regressões próximas cobrem streaming/resultado e contrato OpenAPI. Testes menores usam limite reduzido por monkeypatch;
o caso de 20.000 verifica o valor real sem alterar o teto público.

Uma sonda reproduziu TimeoutError no pool de uma conexão antes da correção, em 3,26 s; log tmp/a8-pool-before.log.
A recuperação foi corrigida e essa regressão passou na seleção final.
Durante depuração, o injetor SQL inicialmente usava nome incorreto de tabela; foi corrigido para events.name, sem alterar o comportamento para esconder falha.
O check OpenAPI detectou exportação anterior à última descrição; o arquivo foi regenerado antes da seleção final.
Repetições e sondas anteriores não entram no total de testes distintos aprovados. Aviso existente Starlette/HTTPX permanece.

Lint/formato, OpenAPI, links/invariantes e whitespace conferidos. Portal: lint dirigido de app/chat/page.tsx e TypeScript sem emissão aprovados.
portal/AGENTS.md foi lido. Guias node_modules/next/dist/docs ausentes na instalação; alteração restrita ao mapa de strings existente, sem API de framework.
Aceite local A8 comprovado. Suíte completa reservada ao fechamento A.
PostgreSQL, concorrência entre processos, runtimes reais, inspeção visual/build e revisão manual CTO/Astra pendentes.
Sem commit, push, PR, deploy ou revisão automática.

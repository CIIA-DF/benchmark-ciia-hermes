# A5 — Expiração de queued e snapshot do run

Data: 30/10/2026. Escopo: A5 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree oficial `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend` conferida.
Testes dirigidos; suíte completa reservada ao fechamento A. Relatório conciso conforme solicitação.

## Falha reproduzida

Um run queued continuava queued ao atingir 300 segundos desde created_at.

```sh
uv run --locked python -m pytest tests/backend/test_a5.py::test_get_expires_at_exact_queue_boundary_once_and_keeps_access_rules --durations=5
```

Antes da correção: uma falha esperada, 5,78 s. GET retornava 200, mas o snapshot mantinha queued em vez de timed_out.
Relógio controlado somente no módulo de execução, sem esperar 300 segundos reais; dados exclusivamente sintéticos.

## Implementação e significado

[ExecutionService](../../services/backend/execution.py) acrescenta RUN_QUEUE_TIMEOUT_SECONDS, inteiro positivo, padrão 300.
O prazo conta desde created_at e é independente de RUN_TIMEOUT_SECONDS, que continua limitando a execução já iniciada.
Zero, negativo ou texto inválido impedem inicialização. Todas as instâncias devem usar configuração operacional coerente.
[.env.example](../../.env.example) publica a nova variável; é necessário fornecê-la ao processo da API para substituir o padrão.

- expire agora seleciona queued vencidos e running vencidos com condições distintas.
- Queued vence quando created_at + prazo <= agora. Estado terminal: timed_out; causa em result.error_code: queue_timeout.
- _timeout_run grava estado/resultado/finished_at e evento done na mesma transação, com a trava do run mantida pelo chamador.
- O done de fila contém status timed_out e error_code queue_timeout. O payload anterior de timeout do worker foi preservado.
- Repetir manutenção/GET não cria novo evento terminal. Não há reexecução automática ou exclusão do run.
- GET conserva histórico, parciais em eventos e artefatos. O prazo de fila não se aplica a um run que já está running.

A expiração é **passiva**, sem scheduler novo: ocorre nos caminhos que executam manutenção, incluindo GET do run, criação, claim, detalhe de conversa e leitura de eventos.
Sem chamadas a esses caminhos, a linha pode continuar armazenada como queued até o próximo processamento.
finished_at registra o instante do processamento; não representa promessa de evento em tempo real no segundo 300.
PostgreSQL usa SKIP LOCKED na manutenção; linhas ocupadas podem ficar para outra passagem. Essa semântica e a concorrência real nesse banco continuam pendentes de homologação.

## Criação, quota e claim

Criação de benchmark e mensagem já executavam expire antes da transação de criação.
Agora a quota A3/A4 também reavalia queued vencidos do operador, sob sua trava, antes de contar capacidade.
Isso cobre a passagem do prazo entre a limpeza inicial e a decisão de quota, sem exigir consulta prévia do operador.

A manutenção inicial usa transação própria, como já acontecia para running. A rechecagem junto à quota participa da transação de criação e acompanha seu rollback se ela falhar.

Claim também executa manutenção inicial e revalida o prazo da candidata depois de verificar grants, antes de atribuir worker/lease.
Candidata que venceu nesse intervalo é encerrada como queue_timeout e não é entregue; o laço pode buscar outra elegível.
Claim direcionado a run expirado retorna 204 quando não há candidata elegível para aquele ID. O próximo polling pode entregar um run fresco.
Não foram adicionados registro de presença ou novas regras de heartbeat: esses temas continuam em A6/A7.

## Workflow e preservação

1. Criação confirma queued com created_at fixo, histórico, mensagem quando aplicável e evento inicial.
2. Antes do prazo, GET devolve queued; claim autorizado pode iniciar a execução.
3. Ao alcançar o prazo sem início, próxima manutenção/rechecagem grava timed_out + queue_timeout + done atomicamente.
4. GET do proprietário retorna RunResponse com 200 e a causa no resultado; 200 confirma a leitura do snapshot, não sucesso da tarefa.
5. SSE transmite o done persistido com a causa e termina por estado terminal.
6. Mudança de estado libera a vaga queued e permite novo envio, incluindo na mesma conversa cujo run expirou.
7. Replay da entrada antiga continua retornando o mesmo run, agora timed_out, com HTTP 202 nos endpoints de criação. Não renova created_at nem ressuscita o run.
8. Outra tentativa de tarefa exige chave nova. Falhas/parciais da execução expirada não passam à memória do agente da execução seguinte.

Nenhum histórico, mensagem, evidência, artefato ou tentativa de ferramenta foi apagado.
Timeout de running continua worker_timeout. Teste mantém running com created_at antigo e lease válido, depois expira a lease e confere parcial, histórico e recibo íntegro.
A rotina de timeout não usa o resultado enviado pelo agente para inventar sucesso ou recebimento pelo cliente.

## Contrato, consumidores e respostas

[StoredResult](../../contracts/execution.py) acrescenta queue_timeout ao enum de saída. Estados do run e campos públicos permanecem iguais.
AgentResult do worker **não** passa a aceitar essa causa: envio forjado de error_code queue_timeout recebe 422.
[app.py](../../services/backend/app.py) e [OpenAPI](../../services/backend/openapi.yaml) documentam prazo e comportamento nos caminhos GET/criação/claim.
[Portal](../../portal/app/chat/page.tsx) recebeu somente uma entrada no mapa de mensagens para explicar a causa em português, sem mudança de fluxo/layout.
Consumidores com enum fechado de resultado precisam atualizar os contratos antes de integrar; backend, agentes, portal e Metodologia devem revisar o significado da causa.

| Situação | HTTP | Estado / código |
| --- | --- | --- |
| GET de queued antes do prazo | 200 | queued; result null |
| GET de fila vencida processada | 200 | timed_out; result.error_code queue_timeout |
| Replay de criação de run já expirado | 202 | Mesmo run_id, timed_out |
| Claim de fila vencida, sem elegível | 204 | Sem lease/execução entregue |
| Claim de candidata fresca | 200 | ClaimedRun; running |
| Lease/orçamento de running vencido | 200 no GET | timed_out; worker_timeout |
| Credencial/perfil/recurso inválidos | 401 / 403 / 404 | Regras anteriores preservadas |
| UUID inválido / causa reservada enviada pelo worker | 422 | validation_error |
| Falha SQL ao persistir timeout/evento | 503 | storage_unavailable; rollback conjunto |

Snapshots privados mantêm no-store. queue_timeout é causa do resultado persistido, não novo código de ToolError ou HTTP 504.
Expiração de fila não prova que um worker/LLM estava desconectado; prova que esta execução não iniciou dentro do prazo observado.

## Testes próprios e seleção dirigida

Novo [test_a5.py](../../tests/backend/test_a5.py): dez casos pytest.

- Fronteira 299,999/300 segundos, evento terminal único, GET/SSE tipados, acesso preservado e recusa de causa reservada no envio do worker.
- Criação de benchmark e chat sem GET anterior: expiração libera quota/conversa; replay não reabre execução; nova memória exclui a pergunta expirada.
- Claim direcionado retira fila vencida sem entrega e polling entrega candidata fresca.
- Prazo atravessado entre manutenção inicial e claim, com revalidação sob trava.
- Prazo atravessado entre manutenção inicial e contagem da quota, sem 429 indevido por essa janela.
- Running com created_at antigo conserva seu prazo próprio; posterior worker_timeout preserva parcial, histórico e artefato verificável pelo GET A1.
- Falha SQL ao inserir done faz rollback de estado/resultado/finished_at; nova passagem produz apenas um terminal.
- GET/expiração disputando com claim em duas aplicações/engines: um terminal e nenhuma atribuição do run vencido.
- Configuração padrão, positiva alternativa e valores inválidos, independente do orçamento de running.

Oito regressões próximas: quota/replay de benchmark A3, três disputas de produtores A4, timeout/memória de running, SSE/deltas e dois testes OpenAPI.

```sh
uv run --locked python -m pytest tests/backend/test_a5.py tests/backend/test_a3.py::test_twentieth_is_allowed_replay_precedes_quota_and_claim_frees_slot tests/backend/test_a4.py::test_queue_races_use_one_operator_lock_for_both_producers tests/backend/test_execution.py::test_lease_expiration_preserves_partial_and_excludes_failed_memory tests/backend/test_execution.py::test_event_replay_sse_cursor_and_result_consistency tests/backend/test_openapi.py --durations=10
```

**18 aprovados em SQLite, 112,98 s (1min53s)**, em uma seleção dirigida: dez próprios e oito próximos.
A reprodução anterior não conta como teste distinto aprovado. Log: tmp/a5-directed.log; código final 0 em tmp/a5-directed.exit.

Maiores fases: preparação 17,62 s no claim que atravessa o prazo; chamada 14,25 s e preparação 13,42 s no caso SSE/deltas.
As fronteiras usam relógio controlado, sem sleep de 300 s. Durações medem a execução local da seleção, não desempenho de agentes ou PostgreSQL.
Um aviso existente de depreciação Starlette/HTTPX permanece.

## Verificações e limites

Lint e formato dos quatro arquivos Python alterados aprovados. OpenAPI regenerado. Diff comparado à cópia anterior ao A5, preservando entregas anteriores.
Portal: `node node_modules/next/dist/bin/next lint --file app/chat/page.tsx` aprovado, sem avisos/erros; `node node_modules/typescript/bin/tsc --noEmit --incremental false` aprovado.
Foi lido portal/AGENTS.md. O diretório de guias node_modules/next/dist/docs não existe no Next instalado 14.2.35; a alteração usa apenas o mapa existente de strings, sem API de framework ou mudança de dependência.

`uv run --locked python -m scripts.export_openapi --check`: aprovado.
`uv run --locked python -m scripts.validate_repository`: aprovado.
`git -c core.safecrlf=false diff --check`: aprovado.
Estado: A5 implementado e verificado localmente por 18 testes dirigidos em SQLite, disponível para revisão manual.
Suíte completa não executada por solicitação explícita; fica para o fechamento A.
PostgreSQL, processos separados, relógios entre hosts, runtimes/LLMs reais, inspeção visual/build do portal e revisão CTO/Astra não executados nesta etapa.
Concorrência local usa threads e duas aplicações sobre SQLite; não homologa travas/isolamento PostgreSQL ou recuperação operacional.
Sem merge de main com alterações locais e autorização restrita ao trabalho local. Sem commit, push, PR, publicação, deploy ou revisão automática.
A6 não iniciado. Estado disponível para revisão manual local, sem aceite global de segurança do backend.

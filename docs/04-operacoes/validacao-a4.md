# A4 — APIs de conversas e quota compartilhada

Data: 30/10/2026. Escopo: A4 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree oficial `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend` conferida.
Testes dirigidos conforme solicitação; suíte completa reservada ao fechamento A. Relatório conciso.

## Reprodução e mudança funcional

Após A3, mensagens queued eram contadas, mas o produtor de mensagens ainda não aplicava o limite.
Com 19 benchmarks e uma mensagem queued do operador, outra conversa aceitava o 21º run com 202.

```sh
uv run --locked python -m pytest tests/backend/test_a4.py::test_message_quota_replay_and_active_conversation_preserve_atomicity --durations=5
```

Antes da correção: uma falha esperada, 14,34 s. O teste exigia 429 e recebeu 202.
Bancos e conteúdo exclusivamente sintéticos.

[ExecutionService.create_run](../../services/backend/execution.py) agora aplica ensure_queue_capacity incondicionalmente aos dois produtores existentes: benchmark e mensagem de chat.
Foi removida somente a exceção de conversation_id que postergava o chat para este bloco.
A quota continua na mesma transação, depois do replay e das validações, sob a trava do principal.

Padrão de 20 queued por operador; RUN_MAX_QUEUED_PER_OPERATOR positivo permanece configurável.
Contagem inclui todos os seus processos, corpus, executores, benchmarks e chats. Running e estados terminais não ocupam a fila.
O envio de mensagens agora retorna 429 resource_limit, retryable true, quando não há vaga.
[app.py](../../services/backend/app.py), [OpenAPI](../../services/backend/openapi.yaml) e o comentário da [configuração](../../.env.example) refletem o comportamento comum.

Modelos, campos públicos, códigos de erro, persistência de memória e migrações permanecem iguais nesta entrega.
Não se acrescentou paginação, contador em memória, reserva de vaga ou redesenho do chat.

## Matriz dos endpoints

| Endpoint | Estado e implementação | Evidência dirigida |
| --- | --- | --- |
| POST /conversations | Preservado; exige operador, grant, contexto/versão e executor válidos; retorna ConversationResponse com 201 | Escopo estrangeiro 403, versão 409, executor desabilitado 503, campo proprietário extra 422; apenas a criação válida persiste |
| GET /conversations | Preservado; lista só do proprietário sob grants atuais; filtro participant_id não concede acesso | Mesmo participante em outro operador não aparece; UUID inválido 422; grant revogado resulta em lista vazia 200 |
| GET /conversations/{id} | Preservado; ConversationDetail tipado com mensagens e runs; snapshot coerente sob finalização | Proprietário estrangeiro/ausente 404, grant revogado 403, UUID inválido 422, mensagem persistida incompatível retorna 500 invalid_response seguro |
| POST /conversations/{id}/messages | Quota comum aplicada; mensagem/run/evento na mesma transação; mantém uma execução queued/running por conversa | 429 sem efeitos; replay 202 mesmo com fila cheia; conflito 409; rollback e concorrência entre duas aplicações |

Os três primeiros endpoints não exigiram mudança funcional: os testes não reproduziram falha nova nesse escopo.
A listagem mantém o limite existente de 100 conversas. participant_id permanece pseudônimo/filtro, sem isolar pessoas que usam a mesma credencial técnica.

## Workflow e relações dos dados

1. POST /conversations valida o contexto autorizado e fixa processo, corpus, requisitos, executor e participante opcional.
2. conversation_id alimenta GET do detalhe e POST de mensagem. GET da coleção ajuda a recuperar apenas as conversas autorizadas do operador.
3. MessageInput contém content e idempotency_key; contexto/executor vêm da conversa persistida, não do envio da mensagem.
4. Criação do run adquire trava do operador. A mesma chave/entrada/conversa recupera o run anterior antes de contar a fila.
5. Outra entrada ou conversa com a mesma chave retorna 409 idempotency_conflict.
6. Nova mensagem exige conversa própria, grant atual e ausência de run queued/running na conversa. Esse conflito continua anterior à quota.
7. Memória do agente usa apenas interações de runs succeeded e a pergunta atual; falhas e parciais não entram na próxima execução.
8. Quota comum é conferida antes das inserções, sob a mesma trava dos benchmarks.
9. Run, mensagem user com run_id/conversation_id e evento inicial são confirmados juntos. Recusa/rollback não deixa mensagem ou run órfão.
10. Worker obtém o run pelo claim e usa seu lease. Claim libera a vaga queued, mas a execução running ainda bloqueia novo envio na mesma conversa.
11. Finalização confirma mensagem assistant e resultado juntos. GET do detalhe associa mensagens somente aos runs presentes no snapshot e preserva coerência com seu estado.
12. Restart conserva participante, mensagens e resultado; participante não é incluído no contexto entregue ao agente.

Repetir o envio não acrescenta mensagem/evento nem ocupa outra vaga. Uma entrada recusada por falta de capacidade pode usar a mesma chave depois que houver vaga.
Criar uma conversa não enfileira execução nem reserva capacidade; a quota é aplicada no envio efetivo.

## Respostas e consumidores

| Situação | HTTP | code / resultado |
| --- | --- | --- |
| Conversa criada | 201 | ConversationResponse |
| Coleção/detalhe autorizados | 200 | Lista / ConversationDetail |
| Mensagem aceita ou replay idêntico | 202 | Mesmo RunResponse no replay |
| Chave reutilizada com entrada/conversa diferente | 409 | idempotency_conflict |
| Outra mensagem com execução ativa na conversa | 409 | conflict |
| Fila compartilhada cheia | 429 | resource_limit; retryable true |
| Credencial ausente/inválida | 401 | unauthorized |
| Worker ou grant revogado no recurso | 403 | forbidden |
| Recurso ausente ou de outro proprietário | 404 | not_found |
| Entrada/UUID fora do contrato | 422 | validation_error |
| Saída persistida fora do modelo | 500 | invalid_response |
| Banco/executor indisponível | 503 | storage_unavailable / executor_unavailable |

A0 preserva envelope seguro, no-store e challenge Bearer. 429 não estima Retry-After porque o momento de consumo da fila é desconhecido.
Sem reenvio automático no servidor. Portal e demais clientes do chat devem apresentar a recusa e preservar chave/entrada ao repetir.
Backend, consumidores do chat e adaptadores devem revisar esse novo ponto de 429 antes de integrar. O código resource_limit já foi introduzido em A3; nenhum enum novo foi acrescentado em A4.

## Testes próprios e regressões próximas

Novo [test_a4.py](../../tests/backend/test_a4.py): nove casos pytest.

- Quota real padrão 20 compartilhada entre benchmark e chat; replay, chave/entrada/conversa incompatível, queued/running ativo, claim e repetição após liberar vaga.
- Três disputas entre aplicações/engines independentes: conversas distintas, mesma conversa e benchmark contra mensagem. Uma única gravação; perdedor recebe 429 ou 409 conforme a regra.
- Duas falhas SQL isoladas: INSERT de mensagem ou do evento inicial. Run/mensagem/evento fazem rollback juntos; a mesma chave pode ser repetida sem duplicar efeitos.
- POST de conversa: escopo, executor, versão, perfil, credencial e rejeição de proprietário fornecido pelo cliente.
- GET da coleção: propriedade, filtro, participante compartilhado entre operadores, recurso estrangeiro e revogação.
- GET do detalhe: modelos aninhados, vínculo mensagem/run, recurso ausente, UUID inválido e saída corrompida com 500 seguro; leitura válida recuperada após restauração do dado sintético.

Oito regressões próximas: limite/replay do benchmark A3, memória isolada de benchmark, falha excluída da memória seguinte, dois momentos de finalização concorrente ao GET, participante após restart e dois testes OpenAPI.

```sh
uv run --locked python -m pytest tests/backend/test_a4.py tests/backend/test_a3.py::test_twentieth_is_allowed_replay_precedes_quota_and_claim_frees_slot tests/backend/test_execution.py::test_memory_and_benchmark_have_separate_contexts tests/backend/test_execution.py::test_lease_expiration_preserves_partial_and_excludes_failed_memory tests/backend/test_run_snapshots.py::test_conversation_snapshot_matches_run_status tests/backend/test_chat_delivery.py::test_participant_survives_restart_and_is_not_agent_context tests/backend/test_openapi.py --durations=10
```

**17 aprovados em SQLite, 83,43 s (1min23s)**, em uma seleção dirigida: nove próprios e oito próximos.
A reprodução anterior não é teste distinto adicional aprovado. Log: tmp/a4-directed.log; código final 0 em tmp/a4-directed.exit.

Maiores chamadas: 8,33 s no cenário de quota do chat e 7,70 s no cenário do benchmark.
Maiores preparações: 7,35 s em snapshot concorrente, 7,11 s em falha/memória e 6,03 s em filtros/revogação.
A amostra não isola causa nem mede desempenho real de agentes. Um aviso existente de depreciação Starlette/HTTPX permanece.

## Verificações e limites

Lint/formato dos três arquivos Python alterados aprovados. Duas linhas longas da descrição foram divididas sem alterar o texto gerado; OpenAPI conferido após esse ajuste.
Diff da implementação comparado à cópia anterior ao A4; trabalho anterior preservado.
`uv run --locked python -m scripts.export_openapi --check`: aprovado.
`uv run --locked python -m scripts.validate_repository`: aprovado.
`git -c core.safecrlf=false diff --check`: aprovado.
Estado: A4 implementado e verificado localmente por 17 testes dirigidos em SQLite, disponível para revisão manual.

Suíte completa não executada por solicitação explícita; fica para o fechamento do bloco A.
Concorrência local usa threads e duas aplicações, não processos separados ou PostgreSQL. PostgreSQL permanece para homologação no bloco H.
Runtimes/LLMs reais, inspeção visual do portal e revisão CTO/Astra não executados. Nenhum código do portal foi alterado.
Quota aplicada aos dois produtores existentes não encerra a proteção global de recursos: expiração queued continua A5; eventos, SSE e tentativas seguem nos seus blocos.
Sem merge de main com alterações locais e autorização restrita ao trabalho local. Sem commit, push, PR, publicação, deploy ou revisão automática.
A5 não iniciado. Estado disponível para revisão manual local, sem aceite global do backend.

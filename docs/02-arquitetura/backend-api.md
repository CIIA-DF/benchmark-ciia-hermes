# API do backend — referência v0.3

Data: 25/10/2026. Responsável: Backend & Tools. Complementa o [TDD](backend-tdd.md).

## Fonte e atualização

O contrato executável é o OpenAPI 3.1 gerado pelo FastAPI a partir dos modelos de
`contracts/` e das anotações em `services/backend/app.py`. A cópia versionada fica em
[`services/backend/openapi.yaml`](../../services/backend/openapi.yaml).

- Com o backend local em execução: `/docs` (Swagger UI) e `/openapi.json`.
- Regenerar após mudar rota ou contrato: `uv run --locked python -m scripts.export_openapi`.
- Conferir sem gravar: `uv run --locked python -m scripts.export_openapi --check`.
  `tests/backend/test_openapi.py` falha se a cópia divergir do código.

Não edite o YAML à mão; altere o código e regenere.

## Autenticação

| Esquema | Cabeçalho | Quem usa |
| --- | --- | --- |
| `BearerAuth` | `Authorization: Bearer <token>` | Rotas de negócio; `/health` e documentação automática são públicos. Token opaco provisionado por `scripts.provision`; o servidor guarda somente o SHA-256. |
| `RunToken` | `X-Run-Token: <run_token>` | Worker, nas tools e em heartbeat/eventos/resultado. Vem de `POST /runs/claim` e vale só para aquela execução enquanto a reserva estiver ativa. |

Perfis: `operator` (chat, conversas, execuções, artefatos) e `worker` (claim, tools,
eventos, resultado), vinculado a um executor. Cada operação confere também a
concessão processo/corpus do worker **e** do dono da execução. Escritas exigem
`can_write` nos dois perfis.

Corpo inválido é rejeitado pelo FastAPI antes da autenticação: uma requisição sem
token e com corpo inválido recebe 422, não 401.

## Rotas

| Método e rota | Perfil | Sucesso | Erros |
| --- | --- | --- | --- |
| `GET /health` | público | 200 | 503 |
| `GET /capabilities` | operator | 200 `CapabilitiesResponse` | 401, 403, 503 |
| `GET /processos` | operator | 200 `Process[]` | 401, 403, 503 |
| `POST /conversations` | operator | 201 `ConversationResponse` | 401, 403, 404, 409, 422, 503 |
| `GET /conversations?participant_id=` | operator | 200 `ConversationResponse[]` | 401, 403, 422, 503 |
| `GET /conversations/{id}` | operator | 200 `ConversationDetail` | 401, 403, 404, 422, 503 |
| `POST /conversations/{id}/messages` | operator | 202 `RunResponse` | 401, 403, 404, 409, 422, 503 |
| `POST /runs` | operator | 202 `RunResponse` | 401, 403, 404, 409, 422, 503 |
| `GET /runs/{id}` | operator | 200 `RunResponse` | 401, 403, 404, 422, 503 |
| `GET /runs/{id}/events` | operator | 200 `text/event-stream` | 401, 403, 404, 422, 503 |
| `GET /artifacts/{id}` | operator | 200 `ArtifactResponse` | 401, 403, 404, 422, 503 |
| `POST /runs/claim` | worker | 200 `ClaimedRun` ou 204 | 401, 403, 422, 503 |
| `POST /runs/{id}/heartbeat` | worker + RunToken | 200 | 401, 403, 409, 422, 503 |
| `POST /runs/{id}/events` | worker + RunToken | 200 `EventReceipt` | 401, 403, 409, 422, 503 |
| `POST /runs/{id}/result` | worker + RunToken | 200 `RunResponse` | 401, 403, 409, 422, 503 |
| `POST /tools/{nome}` (6 tools) | worker + RunToken | 200 | 401, 403, 404, 409, 422, 503 |

Tools: `consultar_processo`, `buscar_documentos`, `ler_documento`,
`consultar_requisitos` (leitura) e `registrar_pendencia`, `salvar_minuta` (escrita).
Todas recebem o `ToolContext` (`run_id`, `process_id`, `corpus_version`,
`requirements_version`), que precisa coincidir com o contexto da execução reservada;
caso contrário, 403. O catálogo entregue ao modelo (`contracts.catalog.tool_catalog()`)
omite esses campos; o cliente HTTP os injeta.

## Erros

Erros de domínio, validação de entrada e banco tratados pela aplicação usam `ToolError`.
404/405 do framework, 500 inesperado e recusas do proxy podem ter outro formato
(ver [auditoria de 28/10](../04-operacoes/auditoria-backend-2026-10-28.md)). Exemplo:

```json
{"code": "idempotency_conflict", "message": "Chave reutilizada com outro conteúdo.",
 "run_id": null, "retryable": false}
```

| HTTP | `code` | Situações |
| --- | --- | --- |
| 401 | `unauthorized` | Token ausente, sem prefixo `Bearer` ou desconhecido. |
| 403 | `forbidden` | Perfil errado, processo/corpus sem concessão, worker sem reserva válida, contexto da tool divergente, perfil sem escrita. |
| 404 | `not_found` | Conversa, run ou artefato inexistente ou de outro operador; processo, documento, página ou checklist ausente. |
| 409 | `conflict` | Run ativo na conversa; run não está `running`; reserva expirada. |
| 409 | `idempotency_conflict` | Mesma chave ou `event_id` com conteúdo diferente; resultado final diferente do já gravado. |
| 409 | `version_mismatch` | `requirements_version` diferente da registrada no processo. |
| 409 | `budget_exceeded` | Nova chamada lógica de tool depois de esgotado `RUN_MAX_TOOL_CALLS` no run (desde a v0.3). |
| 422 | `validation_error` | Corpo/parâmetro inválido, evidência inexistente, requisito fora do checklist, resposta final diferente dos deltas, registro experimental incompatível. |
| 422 | `context_limit` | Histórico da conversa acima de `CHAT_CONTEXT_MAX_CHARS` ou resposta acima de 100.000 caracteres. |
| 503 | `storage_unavailable` | Falha do banco (`retryable: true`). |
| 503 | `executor_unavailable` | Executor fora de `ENABLED_EXECUTORS`. |

Executar uma tool que encontra 404 ou lista vazia não é falha do backend: busca
vazia devolve 200 com `items: []` e o aviso de que isso não prova ausência.

No lado do agente, `AsyncToolClient` devolve `{"error": ...}` para
`validation_error`, `not_found` e `idempotency_conflict` e lança `ToolCallError`
nos demais casos; ver [integração dos agentes](../04-operacoes/integracao-agentes.md).

## Rastreio e orçamento das tools (v0.3)

- **Correlação**: cada chamada lógica leva o cabeçalho opcional `X-Tool-Call-Id`
  (`[A-Za-z0-9_.:-]{1,120}`). O mesmo ID é repetido nas novas tentativas e informado em
  `ExperimentRun.tool_calls[].tool_call_id`. Sem o cabeçalho, o servidor gera um ID; um ID
  inválido recebe 422.
- **Histórico de tentativas** (tabela `tool_calls`, migração 0004): uma linha por tentativa,
  com `tool_call_id`, `attempt`, tool, início, duração, status HTTP, `code`, `replayed`,
  `artifact_id` e o SHA-256 dos argumentos, nunca o conteúdo. Sucessos são gravados na
  transação do efeito; falhas, depois do rollback, em transação própria. Entradas recusadas
  pela validação (422) também são registradas quando a credencial e o `X-Run-Token`
  identificam o run. Só o titular da reserva escreve no histórico de um run. A leitura única
  é `ExecutionService.tool_call_history`.
- **Orçamento**: `RUN_MAX_TOOL_CALLS` limita as chamadas lógicas (`tool_call_id` distintos)
  por run; o padrão 0 desliga o limite. A verificação acontece sob a trava do run, e novas
  tentativas do mesmo ID não consomem orçamento. Ao exceder, a resposta é 409
  `budget_exceeded`, também registrada.

## Fluxos

**Chat (portal → proxy local → API).** `GET /capabilities` e `/processos` →
`POST /conversations` → `POST /conversations/{id}/messages` (202, `status: queued`) →
`GET /runs/{id}/events` em SSE até `done` → `GET /conversations/{id}` para mensagens
persistidas. Em reconexão, `GET /runs/{id}` devolve `partial_answer` e
`last_event_id` consistentes; o SSE recomeça de `after=last_event_id`.

Garantias dos snapshots, sem travar o worker:

- `RunResponse`: status, resultado e `last_event_id` vêm de uma única leitura do run, e
  `partial_answer` contém exatamente os `text_delta` de sequência ≤ `last_event_id`.
  `partial_answer` + os deltas do SSE com `after=last_event_id` reproduzem a resposta sem
  perda nem duplicação.
- `ConversationDetail`: cada mensagem pertence a um run listado, e a mensagem do assistente
  aparece se e somente se o run está `succeeded` no mesmo snapshot.

**Worker (`agents.worker`).** `POST /runs/claim` → `ClaimedRun` com `run_token`,
`lease_seconds` (60 por padrão) e `heartbeat_seconds` (lease/4) → tools e
`POST /events` durante a execução → heartbeat periódico → `POST /result`.
Sem heartbeat, a reserva expira, o run vira `timed_out` (`worker_timeout`) e
as tools seguintes recebem 409. O worker nunca envia heartbeat depois do resultado
final, porque os dois são serializados.

**Benchmark.** `POST /runs` com `task_id`, `split` e `repetition`; não usa
memória de chat. Resultado `succeeded` exige `experiment` (`ExperimentRun`)
coerente com o contexto, o executor e os metadados da tarefa, com
`verified_success` e `evaluator` nulos — a avaliação é feita depois, pela Metodologia.

## Eventos SSE

Cada evento tem `id` igual à sequência persistida. `Last-Event-ID` tem precedência
sobre `?after=`. Comentários `: heartbeat` são enviados a cada ~10 s.

| `event` | `data` | Origem |
| --- | --- | --- |
| `status` | `{"status": "queued"\|"running", "text": "..."}` ou `{"text": "..."}` | Servidor (fila/claim) ou worker |
| `text_delta` | `{"text": "..."}` | Worker; espaços e quebras preservados |
| `tool` | `{"tool", "status": "ok"\|"error", "tool_call_id", "duration_ms", "replayed"}`, mais `code` em falhas e `artifact_id` em escritas | Servidor, a cada tentativa registrada com o run ativo |
| `done` | `{"status": "succeeded"\|"failed"\|"timed_out"}` | Servidor; encerra o fluxo |
| `stream_error` | `{"message", "code"}` | Falha depois de aberto o fluxo; reconectar via snapshot |

## Idempotência

| Operação | Chave | Repetição igual | Repetição diferente |
| --- | --- | --- | --- |
| Mensagem / run | `idempotency_key` por operador | Devolve o mesmo run | 409 `idempotency_conflict` |
| Evento | `event_id` por run | Devolve a mesma `sequence` | 409 |
| Resultado | hash do corpo | Devolve o run encerrado | 409 |
| Escrita de tool | `(run_id, tool, idempotency_key)` | Recibo com `replayed: true` | 409 |

Após timeout de rede, repita com a **mesma** chave. Não gere chave nova para a mesma intenção.

## Exemplo de escrita

```http
POST /tools/salvar_minuta
Authorization: Bearer <token do worker>
X-Run-Token: <run_token do claim>

{"run_id": "8d0c6a8e-6f0e-4d7e-9a43-1f2b3c4d5e6f", "process_id": "PROC-DEMO-001",
 "corpus_version": "synthetic-v1", "requirements_version": "demo-v1",
 "idempotency_key": "minuta-1", "content": "Minuta fictícia fundamentada.",
 "evidence": [{"document_id": "DOC-1", "chunk_id": "DOC-1:p1:0", "page": 1}],
 "evidence_note": "Trecho da página 1."}
```

```json
{"run_id": "8d0c6a8e-6f0e-4d7e-9a43-1f2b3c4d5e6f", "process_id": "PROC-DEMO-001",
 "corpus_version": "synthetic-v1", "requirements_version": "demo-v1",
 "artifact_id": "f860e0eb-af19-4edd-a00b-a898384474dc",
 "persisted_at": "2026-10-25T14:02:11.418000+00:00", "content_sha256": "<64 hex>", "replayed": false}
```

Os identificadores de documento e chunk acima são ilustrativos; use os devolvidos por
`buscar_documentos`/`ler_documento`.

## Relação com a proposta de duas camadas

A [proposta](proposta-benchmark-duas-camadas.md) está em revisão e, pelo PRD, não amplia
esta entrega. O que a API já atende:

- Camada 1: Hermes e LangGraph usam as mesmas rotas REST e o mesmo catálogo. A proposta
  cita três tools; a API tem seis, incluindo as duas escritas idempotentes que a proposta
  lista como próximo passo (não há mais respostas 501; o código `not_implemented` continua
  no enum por compatibilidade, sem uso).
- Métricas de eficiência: `ExperimentRun` traz `latency_ms`, `tool_calls` com duração,
  tokens e custo; os eventos `tool` registram cada chamada no servidor.
- Conformidade de acesso: escopo processo/corpus e contexto da execução são impostos pelo
  servidor, não pelo modelo.

Não implementado, e fora do escopo do PRD: cache de tools (Redis/LRU), cache semântico e
um campo explícito para separar rodadas frias e quentes. Se a coordenação aprovar a
proposta, a marcação pode usar `ExperimentRun.parameters` (por exemplo `"cache": "cold"`)
sem mudar o contrato. Essa decisão é da Metodologia.

## consultar_processo — T1

O processo retornado precisa coincidir com o contexto autenticado; o inventário
não admite document_id duplicado e seus documentos são conferidos contra o escopo
persistido. Clientes rejeitam também envelope coerente de outra execução.
500 invalid_response indica inconsistência interna, sem eco de dados e sem retry
automático. Não confundir com 422 de entrada, 409 de versão ou 503 do banco.
Cobertura e nota são preservadas; inventário vazio não prova ausência no SEI.
[Evidências e workflow T1](../04-operacoes/validacao-t1-2026-10-28.md).

## buscar_documentos — T2

Chunks retornados pertencem ao processo/corpus, têm IDs únicos e respeitam limit.
Clientes conferem o contexto completo da requisição. Busca continua substring
literal com escape de curingas e filtros anteriores ao limite. Lista vazia é 200;
banco indisponível é 503; resultado interno inválido é 500 invalid_response.
Comportamento Unicode depende do banco/locale; não há normalização nova.
[Evidências, workflow e portabilidade T2](../04-operacoes/validacao-t2-2026-10-28.md).

## Correção T1-R — processo armazenado inválido

A leitura compartilhada de processo valida o payload antes de acessar seus campos.
500 invalid_response é documentado nas seis tools e nas criações de conversa,
execução e mensagem que consultam esse processo. Recurso ausente é 404; versão
válida incompatível é 409. Nas tools, a reserva lógica e a tentativa de falha
permanecem auditáveis. Outros erros inesperados/framework continuam fora dessa
garantia específica, até A0. [Evidências T1-R](../04-operacoes/validacao-t1-r.md).

## ler_documento — T3

Documento, contexto e páginas são conferidos no servidor e nos clientes. Páginas
solicitadas retornam em ordem documental crescente; numeração pode ter lacunas.
Documento armazenado inconsistente gera 500 invalid_response sem conteúdo;
documento/página ausente mantém 404. Sem filtro, retorna todas as páginas
armazenadas. sha256 permanece do documento completo. Não comprova leitura humana
ou completude do processo original. [Registro T3](../04-operacoes/validacao-t3.md).

## consultar_requisitos — T4

Checklist retornado é não vazio, tem IDs únicos e pertence ao processo/corpus e
requirements_version do run. Servidor confere payload contra chave persistida;
clientes validam contrato e contexto da resposta. Ausente é 404; payload inválido
é 500 invalid_response auditado, sem conteúdo rejeitado; falha SQL é 503
retryable=true. Importação administrativa continua imutável. O ID consultado
pode alimentar registrar_pendencia no mesmo escopo; não atesta homologação
metodológica. [Registro T4 e catálogo de respostas](../04-operacoes/validacao-t4.md).

## registrar_pendencia — T5

Requisito e fontes são conferidos no escopo antes da escrita. Ausência/referência
inválida permanece 422; payload armazenado inconsistente gera 500 invalid_response
seguro. Recibo e efeito são conferidos antes do commit, no replay e na releitura
independente; chave com outra entrada válida mantém 409. 503 após commit pode
significar efeito existente: repetir com os mesmos IDs/corpo ou consultar artefato
como operador, conforme o estado do run. Cliente de pendências confere contexto e
hash do conteúdo. WriteReceipt exige UUID e timestamp com fuso, também nos seus
consumidores compartilhados. Resultado do worker documenta 500 para fontes
armazenadas inconsistentes, sem encerramento parcial do run.
[Catálogo de respostas, evidências e limitações T5](../04-operacoes/validacao-t5.md).

## salvar_minuta — T6

Reutiliza o escritor transacional comum e a validação de fontes/recibo de T5.
Clientes passam a conferir contexto completo e hash do conteúdo da minuta usando
WriteInput do catálogo, rejeitando sucesso inconsistente sem retry. JSON, rotas e
códigos permanecem iguais. 422 para entrada/referência inválida, 500 seguro para
inconsistência armazenada e 503 transitório continuam distintos; após commit,
falha de confirmação pode deixar efeito existente. Retry conserva IDs/corpo.
Minuta não depende de requisito ou pendência anterior. [Workflow, respostas e limites T6](../04-operacoes/validacao-t6.md).

## Rastreamento compartilhado — F0

Requisições das seis tools recebem UUID físico interno, com fases e resposta
preparada separados do efeito e do ID lógico. O recebimento pelo cliente permanece
desconhecido. Rotas, respostas e cabeçalhos públicos não mudaram. O ledger anterior
preserva estágios, sem equivaler a requisições; novos consumidores devem usar a
fonte canônica física. [Fluxo, compatibilidade e limites F0](../04-operacoes/validacao-f0.md).

## consultar_processo — aceite F1

Rastreamento F0 integrado sem alteração da regra de negócio T1/T1-R. Cada consulta
observada usa tentativa física própria; reserva/argumentos e resposta preparada
são conferidos no banco. Leitura não confirma artefato nem recebimento pelo cliente.
200 vazio, 404 ausente, 409 de versão, 500 seguro e 503 continuam distintos.
[Workflow, contratos e evidências F1](../04-operacoes/validacao-f1.md).

## buscar_documentos — F2

U+0000 não é permitido em query: retorna 422 validation_error seguro antes da
consulta SQL, sem remover o caractere. Reserva/orçamento e tentativa física seguem
as regras existentes de atribuição. Busca literal válida, Unicode, filtros, limite,
200 vazio e 503 real do banco permanecem distintos. OpenAPI e catálogo publicam o
padrão do SearchInput. [Matriz e portabilidade F2](../04-operacoes/validacao-f2.md).

## ler_documento — aceite F3

T3 preservado, rastreamento F0 conferido. Documento/contexto, páginas exatas, ordem e hash integral continuam validados.
Leitura integral/parcial mantém 200; ausências, entradas inválidas, corrupção e falha SQL mantêm códigos distintos.
Leitura não cria artefato nem comprova completude do arquivo original. [Evidências F3](../04-operacoes/validacao-f3.md).

## consultar_requisitos — aceite F4

T4 preservado e integração F0 conferida. Checklist válido retorna 200; ausente, 404;
corrompido, 500 seguro; falha SQL, 503. Consulta não confirma artefato nem recebimento pelo cliente.
Isolamento de processo/corpus/versão e consumo na pendência foram exercitados. [Evidências F4](../04-operacoes/validacao-f4.md).

## registrar_pendencia — F5

Rastreamento físico e fases F0 preservados. Integridade extraída para validate_artifact;
fachada do escritor mantém conferência do pedido, requisito, fontes, rollback e replay.
GET não mudou. Corrupção mantém 500 seguro; conflito legítimo, 409; falha SQL, 503.
[Evidências e limites F5](../04-operacoes/validacao-f5.md).

## salvar_minuta — aceite F6

Escritor comum F5 e fases F0 preservados. Concorrência e retry mantêm um efeito.
Cliente confere contexto/hash; minuta não exige checklist ou pendência anterior.
[Matriz, regressões e limites do bloco F](../04-operacoes/validacao-f6.md). APIs seguintes aguardam revisão manual.

## A0 — comportamento HTTP compartilhado

Corpo máximo: 1 MiB (1.048.576 bytes), contado antes da validação do endpoint, inclusive em partes.
Excesso retorna 413 payload_too_large. 405 method_not_allowed preserva Allow.
401 inclui challenge Bearer quando ausente. Respostas privadas usam Cache-Control: no-store.
Erros do framework usam ToolError, sem detail arbitrário. Outros status explícitos usam http_error.
Saída incompatível com response_model retorna 500 invalid_response; falha inesperada anterior aos cabeçalhos retorna 500 internal_error.
Falhas de entrada e banco preservam 422 validation_error e 503 storage_unavailable.
Depois da abertura SSE, falhas produzem stream_error e encerram o fluxo, mantendo o 200 já enviado.
[Catálogo, workflow e limitações A0](../04-operacoes/validacao-a0.md).

## A1 — GET /artifacts/{id}

Após autenticação, propriedade e grants, valida integridade contra o contexto do run persistido.
Ferramenta, payload canônico, recibo, UUIDs, versões, chave e hashes incompatíveis produzem 500 invalid_response seguro.
Mantém ArtifactResponse, ausência/proprietário estrangeiro 404, worker/grant revogado 403 e banco 503.
Leitura não exige can_write ou lease ativo. [Workflow e testes A1](../04-operacoes/validacao-a1.md).

## A2 — POST /runs/{id}/result

Quando experiment é enviado, valida IDs únicos e conjunto completo das chamadas atribuídas ao run, ferramentas, sucesso compatível e artefatos vinculados ao efeito da chamada.
persisted_artifact_ids deve coincidir com os IDs não nulos das chamadas, sem duplicações; efeitos desconhecidos pelo cliente permanecem no histórico observado.
Cliente pode declarar error mesmo com 200/efeito no servidor. HTTP desconhecido não é convertido em prova de recebimento. Durações não são comparadas.
Divergência retorna 422 validation_error sem encerramento. Corrupção do artefato referenciado retorna 500 invalid_response.
Deltas, autenticação, lease e replay terminal idêntico preservados. [Regras completas e testes A2](../04-operacoes/validacao-a2.md).

## A3 — POST /runs com quota do operador

Padrão de 20 queued por operador, configurável por RUN_MAX_QUEUED_PER_OPERATOR positivo. Contagem inclui outros processos, corpus, executores e kinds; running/terminais não ocupam a fila.
Replay da mesma chave/entrada vem antes da quota e conserva run_id. Outra entrada mantém 409 idempotency_conflict.
Fila cheia retorna 429 resource_limit, retryable true, sem run/evento novo. Mantém no-store e não estima Retry-After.
Validações de acesso/contexto anteriores à quota e atomicidade preservadas. Desde A4, a regra também se aplica ao envio de mensagens.
[Workflow, configuração e testes A3](../04-operacoes/validacao-a3.md).

## A4 — APIs de conversas

POST /conversations valida contexto/executor e concede somente conversa do operador. GET da coleção/detalhe mantém proprietário e grants; participant_id não concede acesso.
POST /conversations/{id}/messages compartilha a quota de fila com POST /runs. Sem vaga retorna 429 resource_limit, retryable true, sem mensagem/run/evento parcial.
Replay idêntico precede quota; outra entrada/conversa com a chave gera 409 idempotency_conflict. Outra mensagem em conversa com queued/running mantém 409 conflict.
Memória, snapshots tipados e limite existente da listagem foram preservados. [Matriz e testes A4](../04-operacoes/validacao-a4.md).

## A5 — timeout da fila e snapshot

GET /runs/{id} processa queued com created_at + RUN_QUEUE_TIMEOUT_SECONDS <= agora; padrão 300 s, positivo. Retorna 200 com status timed_out e result.error_code queue_timeout.
Criação e claim também processam expiração; há rechecagem junto à quota e antes da atribuição de worker. Claim não entrega fila vencida e conserva 204 quando não há candidata elegível.
Replay antigo devolve o mesmo run terminal, com 202 na criação; não renova prazo nem inicia outra execução. Timeout de running mantém worker_timeout.
Done de fila contém error_code queue_timeout. Dados anteriores são preservados e consumidores de StoredResult precisam reconhecer a causa.
A manutenção é passiva; finished_at registra processamento, sem scheduler novo. [Workflow, limites e testes A5](../04-operacoes/validacao-a5.md).

## A6 — polling do worker

POST /runs/claim registra presença durável após reler o perfil atual sob trava, inclusive quando retorna 204.
Mantém executor, grants, exclusividade e rechecagem da fila expirada. Não prova saúde de LLM.
[Relatório A6](../04-operacoes/validacao-a6.md).

## A7 — renovação do worker

POST /runs/{id}/heartbeat renova presença e lease juntos após validar perfil atual, executor, credencial, grants e prazo.
Lease inválido retorna 403; execução terminal/vencida retorna 409, sem renovação. [Relatório A7](../04-operacoes/validacao-a7.md).

## A8 — eventos limitados

POST /runs/{id}/events mantém tipos e idempotência. Teto 20.000 inclui todos os produtores e reserva a última vaga para done.
Excesso não terminal retorna 429 resource_limit, retryable false, com run encerrado failed/event_limit. Consulte GET; SSE transmite o terminal.
Tools seguem o mesmo teto; efeitos não confirmados sofrem rollback. [Detalhes e evidências A8](../04-operacoes/validacao-a8.md).

## A9 — limite de SSE

GET /runs/{id}/events admite até cinco leases válidos por operador, compartilhados no banco entre processos.
Excesso retorna 429 resource_limit antes do stream. Leases de 30 s são renovados e recuperados após abandono.
Término/erro/desconexão libera em finally; falha SQL de limpeza depende do TTL. Last-Event-ID/after e stream_error preservados.
[Relatório A9](../04-operacoes/validacao-a9.md).

## A10 — capabilities

GET /capabilities separa enabled/available de worker_recent (janela inclusiva de 60 s) e last_seen_at, em escopo autorizado comum.
Modelo remoto desconhecido é null, com configuration_known false. Presença não comprova inferência ou conexão atual.
[Contrato, workflow e evidências A10](../04-operacoes/validacao-a10.md).

## A11 — alcance do health

GET /health confirma conexão e SELECT 1 com 200; falha SQL/conexão retorna 503 storage_unavailable seguro.
Não verifica schema completo, worker ou LLM. Modelo público preservado. [Evidências A11](../04-operacoes/validacao-a11.md).

## A12 — listagem de processos

GET /processos valida estrutura e identidade de cada payload autorizado, sem lista parcial em caso de corrupção.
Mantém vazio 200; inconsistência retorna 500 invalid_response seguro. [Relatório A12](../04-operacoes/validacao-a12.md).

## A13 — quota das tools HTTP

Cada uma das seis rotas mantém schemas, lease e ID lógico. Até 1.000 admissões físicas por run, agregadas entre tools e incluindo entradas inválidas/retries.
Excesso retorna 429 resource_limit, retryable false; o recebimento recusado continua registrado. Executor incompatível recebe 403.
O teto não encerra o run nem apaga auditoria. [Catálogo individual, workflow e evidências A13](../04-operacoes/validacao-a13.md).

## Fechamento local do bloco A

A0–A13 verificados em SQLite por 390 testes na suíte completa, executada após o aceite A13.
[Relatório consolidado com workflow, catálogo público e limitações](../04-operacoes/validacao-a-fechamento.md).
PostgreSQL, runtimes reais e revisão manual continuam pendentes; não há autorização de deploy.

# API do backend — referência v0.2

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
| `BearerAuth` | `Authorization: Bearer <token>` | Todas as rotas, exceto `/health`. Token opaco provisionado por `scripts.provision`; o servidor guarda somente o SHA-256. |
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

Todo 4xx/5xx usa o mesmo corpo `ToolError`:

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
| 422 | `validation_error` | Corpo/parâmetro inválido, evidência inexistente, requisito fora do checklist, resposta final diferente dos deltas, registro experimental incompatível. |
| 422 | `context_limit` | Histórico da conversa acima de `CHAT_CONTEXT_MAX_CHARS` ou resposta acima de 100.000 caracteres. |
| 503 | `storage_unavailable` | Falha do banco (`retryable: true`). |
| 503 | `executor_unavailable` | Executor fora de `ENABLED_EXECUTORS`. |

Executar uma tool que encontra 404 ou lista vazia não é falha do backend: busca
vazia devolve 200 com `items: []` e o aviso de que isso não prova ausência.

No lado do agente, `AsyncToolClient` devolve `{"error": ...}` para
`validation_error`, `not_found` e `idempotency_conflict` e lança `ToolCallError`
nos demais casos; ver [integração dos agentes](../04-operacoes/integracao-agentes.md).

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
| `tool` | `{"tool", "status": "ok", "duration_ms"}` ou `{"tool", "status", "artifact_id"}` | Servidor, após tool confirmada |
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

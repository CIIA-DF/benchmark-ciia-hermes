# Referência vigente das APIs — bloco D

Consolidação de 31/10/2026, worktree oficial `team/backend`. Esta referência descreve o código local F/A/I; não concede homologação PostgreSQL, de infraestrutura ou de agentes reais. [Estado e evidências](../04-operacoes/backend-estado-atual.md). A [referência anterior](backend-api.md) permanece histórica.

## Fontes e versões

[OpenAPI versionado](../../services/backend/openapi.yaml), [modelos de execução](../../contracts/execution.py), [modelos das ferramentas](../../contracts/models.py) e [rotas](../../services/backend/app.py) são as fontes executáveis. `/docs`, `/redoc` e `/openapi.json` permitem exploração local. Não editar YAML manualmente.

| Identificador | Valor atual | Significado |
| --- | --- | --- |
| API, `info.version` | `0.3.0` | Versão declarada pela aplicação; não atesta homologação. |
| `HealthResponse.contract_version` | `0.3` | Família do protocolo backend/tools. |
| Projeto em `pyproject.toml` | `0.2.0` | Metadado do projeto; `uv` usa `package=false`. Não existe release independente de contracts comprovada nesta entrega. |
| `ExperimentRun.contract_version` | `0.1` | Registro experimental interno, preservado no protocolo de execução. |
| `export_chat.export_version` | `2` | Exportação canônica por histórico persistido; [formato E](../04-operacoes/exportacao-canonica.md), atualizado em 02/11/2026. |

A expressão histórica “envelope v0.2” designa a evolução do protocolo; não acrescenta um campo de versão ao `AgentResult`. D não altera números de versão nem declara novo pacote publicado. [ADR de consolidação](../05-decisoes/010-documentacao-interfaces.md).

## Regras comuns das operações

- Operador: `Authorization: Bearer TOKEN_OPERADOR`. Worker: credencial própria vinculada ao executor. Tokens são placeholders; nunca gravar credenciais reais em exemplos ou logs.
- Worker reservado: acrescentar `X-Run-Token` recebido no claim. Rotas de tools, heartbeat, POST de eventos e resultado exigem esse cabeçalho. Não confundir token da reserva com token do principal.
- Operador consulta somente seus runs/conversas/artefatos com concessões atuais. Filtro `participant_id` não autentica a pessoa. Tools conferem contexto e concessões do worker e proprietário; escritas exigem `can_write` de ambos.
- Enviar `Content-Type: application/json` nos corpos JSON. UUIDs de caminho devem vir das respostas reais. Exemplos abaixo são estruturalmente válidos, mas IDs/versões sintéticos devem ser substituídos pelos retornados no ambiente.
- Respostas privadas recebem `Cache-Control: no-store`; 401 inclui `WWW-Authenticate: Bearer`; 405 conserva `Allow`. O limite de corpo da API é 1 MiB, inclusive em partes.
- Os erros JSON do backend usam `ToolError`: `code`, `message`, `run_id` nullable e `retryable`. Entrada rejeitada, SQL e segredos não são devolvidos. Após abrir SSE, erros são eventos `stream_error`, não uma troca retroativa do status HTTP.
- A ordem importa: quota física atribuível pode recusar antes do corpo; corpo excedido gera 413; validação de corpo pode gerar 422 antes da autenticação do handler. Não presumir 401 para todo corpo inválido sem token.

```json
{"code":"idempotency_conflict","message":"Identificador reutilizado.","run_id":null,"retryable":false}
```

| HTTP | Código e ação |
| --- | --- |
| 401 | `unauthorized`: fornecer credencial válida. |
| 403 | `forbidden`: conferir perfil, escopo, executor, contexto e reserva; não insistir automaticamente. |
| 404 | `not_found`: recurso ausente ou ocultado por propriedade. |
| 405 | `method_not_allowed`: usar método indicado por `Allow`. |
| 409 | `conflict`, `version_mismatch`, `idempotency_conflict`, `budget_exceeded`: corrigir causa; não trocar ID para contornar orçamento. |
| 413 | `payload_too_large`: reduzir corpo; sem efeito de domínio. |
| 422 | `validation_error`, `context_limit`: corrigir entrada; NUL (U+0000) é inválido na busca e, desde 22/11/2026, em todo texto livre ([P3](../../contracts/README.md#p3--textos-livres-sem-u0000-22112026)). |
| 429 | `resource_limit`: fila/SSE permitem retry; teto físico/eventos não permite retry automático (`retryable=false`). |
| 500 | `invalid_response` para saída inconsistente; `internal_error` para falha inesperada. Não repetir automaticamente sucesso inválido. |
| 503 | `storage_unavailable` ou `executor_unavailable`: observar `retryable` e configuração. |

## Limites, estados e relógios

| Limite | Padrão / regra |
| --- | --- |
| Fila por operador | 20 queued; `RUN_MAX_QUEUED_PER_OPERATOR`; chat e benchmark compartilham quota. Replay precede quota. |
| Fila | 300 s desde criação; `RUN_QUEUE_TIMEOUT_SECONDS`; expiração passiva por consulta/criação/claim. Não há scheduler garantido. |
| Lease do worker | 60 s; `RUN_LEASE_SECONDS`; heartbeat recomendado `max(1, lease//4)`. |
| Duração total | 300 s desde início; `RUN_TIMEOUT_SECONDS`; heartbeat não reinicia orçamento. |
| Contexto de chat | 100.000 caracteres; `CHAT_CONTEXT_MAX_CHARS`; sem resumo/truncamento silencioso. |
| Eventos | 20.000 por run; última vaga reservada a encerramento. Legado acima do teto é preservado. |
| SSE | 5 leases por operador, entre processos; TTL 30 s, renovação a partir da metade do prazo. |
| Tentativas físicas de tool | 1.000 atribuíveis por run; inclui erros/retries. Recusas continuam registradas acima do teto. Não é limite global de tráfego anônimo. |
| Chamadas lógicas | `RUN_MAX_TOOL_CALLS`, padrão 0 sem teto; identidade já reservada não é cobrada outra vez. |
| Busca | query 1–200 caracteres; limit 1–20; substring literal, `%` e `_` literais. |
| Evento do worker | texto 1–4.000 caracteres; resposta final até 100.000 caracteres. |

Estados: `queued`, `running`, `succeeded`, `failed`, `timed_out`. Causas do servidor incluem `queue_timeout`, `worker_timeout`, `event_limit`; o worker não pode enviá-las como causas próprias. Timeouts preservam histórico e efeitos confirmados. Não há reexecução automática do run.

A correção local A7 revalida prazo após travas/concessões e desfaz presença em caso de vencimento. Sua existência no código não substitui revisão manual ou prova de espera por trava em PostgreSQL; veja o índice de estado.

## Identidades e evidências

| Conceito | Origem e significado |
| --- | --- |
| `run_id` | Servidor, identifica execução. |
| `tool_call_id` | Cliente via `X-Tool-Call-Id`, opcional; servidor gera se ausente. Padrão `[A-Za-z0-9_.:-]{1,120}`. Repetir nas retentativas. Desde 22/11/2026 a resposta das tools devolve o ID efetivo no cabeçalho `X-Tool-Call-Id` (gerado ou enviado), para que o cliente o declare em `ExperimentRun.tool_calls`; valor inválido continua 422, sem eco. |
| Chamada lógica | `(run_id, tool_call_id)` em `logical_tool_calls`; vincula ferramenta/hash antes de consultar domínio. Falha de domínio não libera identidade/orçamento. |
| Tentativa física | UUID do servidor em `physical_tool_attempts`, por requisição de rota tool reconhecida; não é fornecido pelo cliente. Atribuição depende de credencial/reserva, não do run alegado no corpo. |
| Fases | `started`, `effect_confirmed`, `completed`/`failed`/`interrupted`, vinculadas ao UUID físico. |
| Efeito | Artefato confirmado, inclusive replay, com fase transacional. Não equivale a sucesso metodológico. |
| Resposta | `http_status` descreve resposta preparada. `client_received=null` significa desconhecido, não falha nem confirmação de entrega. |
| Ledger legado | `tool_calls` contém etapas; uma requisição pode produzir mais de uma linha. Não contar como requisições nem somar às tentativas físicas. |
| Chave de escrita | `(run_id, tool, idempotency_key)`; mesma entrada recupera recibo, outra entrada retorna 409. Diferente do ID lógico. |

Reserva lógica confirma antes do domínio. Efeito ocorre em transação própria; falha registra tentativa após rollback. Falha de releitura pós-commit pode produzir HTTP 503 com artefato existente. Retry conserva corpo, ID lógico e chave; pode recuperar o recibo com `replayed=true` sem duplicar efeito. GET de artefato confere hashes, payload, recibo, contexto e identidade.

`ExperimentRun` é relato do agente. O resultado reconcilia IDs/ferramentas/artefatos com evidência do servidor e recusa chamadas inventadas. Erro do cliente pode coexistir com efeito; duração cliente/servidor não precisa coincidir. `verified_success`/`evaluator` permanecem nulos na submissão. E exporta histórico canônico v2; indicadores e ganhos experimentais continuam pendentes em O.

## Configuração, presença e prontidão

`available` mantém significado legado de configuração habilitada; `enabled` explicita isso. `worker_recent` exige observação válida dentro de 60 s, inclusive a fronteira, com escopo atual compartilhado. `last_seen_at` pode ser null; `model=null` e `configuration_known=false` não são inferidos do ambiente da API. Polling 204 também registra presença.

`GET /health` executa consulta real ao banco. `{"status":"ok","contract_version":"0.3"}` não comprova worker, modelo, GPU ou integração Hermes/LangGraph. Presença também não comprova inferência.

## Referência por endpoint

As respostas, parâmetros e modelos abaixo foram conferidos contra o OpenAPI local. Campos completos, restrições e nulabilidade estão nos schemas ligados acima; as regras comuns aplicam-se a cada ficha. Os exemplos versionados estão em [backend-api-exemplos.json](backend-api-exemplos.json).

### GET `/health`

Verifica API e banco

Autenticação: **público**.

Executa SELECT 1 no banco configurado. 200 confirma essa consulta; falha SQL retorna 503 storage_unavailable. Não verifica schema completo, fila, workers, modelos ou inferência de LLM.

Parâmetros: nenhum.

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | HealthResponse |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /health`. Aplicar os cabeçalhos do perfil acima.

### GET `/ready`

Verifica se o schema do banco está na revisão esperada

Autenticação: **público**.

Compara a revisão Alembic aplicada com a head do código, sem migrar. Diferença ou banco sem controle de versão retorna 503 storage_unavailable retryable (por exemplo, migração ainda em curso). `/health` continua só testando a conexão. Não verifica fila, workers, modelos ou inferência.

Parâmetros: nenhum.

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ReadinessResponse |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /ready`.

### GET `/capabilities`

Configuração dos executores, presença observada e permissão de escrita

Autenticação: **operator**.

available mantém o significado legado de configuração habilitada, igual a enabled. worker_recent indica polling/heartbeat autorizado nos últimos 60 s, em escopo concedido ao operador. Não comprova inferência. Modelo remoto desconhecido é null e configuration_known é false; não são inferidos do ambiente da API.

Parâmetros: nenhum.

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | CapabilitiesResponse |
| 401 | ToolError |
| 403 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /capabilities`. Aplicar os cabeçalhos do perfil acima.

### GET `/processos`

Processos e corpus concedidos ao operador

Autenticação: **operator**.

Lista vazia autorizada retorna 200. Payload persistido deve ser válido e corresponder à identidade da linha concedida; inconsistência retorna 500 invalid_response seguro, sem lista parcial.

Parâmetros: nenhum.

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | Process[] |
| 401 | ToolError |
| 403 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /processos`. Aplicar os cabeçalhos do perfil acima.

### POST `/conversations`

Cria conversa fixando processo, corpus, requisitos e executor

Autenticação: **operator**.

Parâmetros: nenhum.

Entrada: `ConversationInput`.

| HTTP | Saída |
| --- | --- |
| 201 | ConversationResponse |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /conversations`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1"
}
```

### GET `/conversations`

Lista conversas do operador; filtro de participante não concede acesso

Autenticação: **operator**.

Parâmetros: `participant_id` (query, opcional).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ConversationResponse[] |
| 401 | ToolError |
| 403 | ToolError |
| 422 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /conversations`. Aplicar os cabeçalhos do perfil acima.

### GET `/conversations/{conversation_id}`

Conversa com mensagens e execuções

Autenticação: **operator**.

Parâmetros: `conversation_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ConversationDetail |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 422 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /conversations/00000000-0000-4000-8000-000000000003`. Aplicar os cabeçalhos do perfil acima.

### POST `/conversations/{conversation_id}/messages`

Envia mensagem e enfileira execução de chat

Autenticação: **operator**.

Repetir a mesma `idempotency_key` com a mesma entrada devolve o run existente antes da quota. Só um run ativo por conversa; outro envio recebe 409 `conflict`. Compartilha com POST /runs o limite de queued por operador, padrão 20, configurável por RUN_MAX_QUEUED_PER_OPERATOR. Fila cheia retorna 429 `resource_limit`, sem gravar mensagem, run ou evento. Gravação dos três é atômica.

Parâmetros: `conversation_id` (path, obrigatório).

Entrada: `MessageInput`.

| HTTP | Saída |
| --- | --- |
| 202 | RunResponse |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /conversations/00000000-0000-4000-8000-000000000003/messages`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "content": "Analisar inventário sintético.",
  "idempotency_key": "mensagem-1"
}
```

### POST `/runs`

Enfileira execução de benchmark, sem memória de chat

Autenticação: **operator**.

Limite padrão de 20 runs queued por operador, contando todos os seus processos, corpus e executores. Configurável por RUN_MAX_QUEUED_PER_OPERATOR. Replay da mesma chave/entrada precede a quota; entrada diferente mantém 409. Fila cheia retorna 429 resource_limit, sem criar run ou evento. Queued vencido é expirado antes da quota, sem exigir GET prévio.

Parâmetros: nenhum.

Entrada: `RunInput`.

| HTTP | Saída |
| --- | --- |
| 202 | RunResponse |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /runs`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1",
  "task": "Analisar inventário sintético.",
  "task_id": "DEV-001",
  "idempotency_key": "execucao-1"
}
```

### POST `/runs/claim`

Reserva a próxima execução do executor

Autenticação: **worker**.

Devolve `run_token`, que deve ir no cabeçalho `X-Run-Token` das tools, eventos, heartbeat e resultado. Queued vencido não é entregue; a expiração é revalidada sob a trava antes de atribuir o worker. Polling autorizado registra presença observada, inclusive quando retorna 204 sem trabalho.

Parâmetros: nenhum.

Entrada: `ClaimInput`.

| HTTP | Saída |
| --- | --- |
| 200 | ClaimedRun |
| 204 | Sem corpo |
| 401 | ToolError |
| 403 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /runs/claim`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "executor": "simulation"
}
```

### GET `/runs/{run_id}`

Snapshot consistente de status, texto parcial e cursor

Autenticação: **operator**.

Queued expira após 300 s desde created_at, configuráveis por RUN_QUEUE_TIMEOUT_SECONDS. Retorna timed_out com result.error_code queue_timeout, preservando histórico, parciais e artefatos. A regra também vale em criação e claim.

Parâmetros: `run_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | RunResponse |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 422 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /runs/00000000-0000-4000-8000-000000000001`. Aplicar os cabeçalhos do perfil acima.

### POST `/runs/{run_id}/heartbeat`

Renova a reserva da execução

Autenticação: **worker + X-Run-Token**.

Renova lease e presença observada atomicamente para o worker atual autorizado, com executor compatível. Lease vencido ou execução terminal não renova.

Parâmetros: `run_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | HeartbeatResponse |
| 401 | ToolError |
| 403 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /runs/00000000-0000-4000-8000-000000000001/heartbeat`. Aplicar os cabeçalhos do perfil acima.

### POST `/runs/{run_id}/events`

Publica status ou trecho de resposta; idempotente por event_id

Autenticação: **worker + X-Run-Token**.

Teto de 20.000 eventos por run, incluindo eventos do servidor e tools. A última vaga é reservada ao done. Novo evento sem capacidade retorna 429 resource_limit e encerra o run com result.error_code event_limit; consulte o snapshot. Replay idêntico de evento já aceito não consome vaga enquanto o run estiver ativo.

Parâmetros: `run_id` (path, obrigatório).

Entrada: `AgentEvent`.

| HTTP | Saída |
| --- | --- |
| 200 | EventReceipt |
| 401 | ToolError |
| 403 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /runs/00000000-0000-4000-8000-000000000001/events`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "event_id": "00000000-0000-4000-8000-000000000002",
  "kind": "text_delta",
  "text": "Resposta sintética."
}
```

### GET `/runs/{run_id}/events`

Fluxo SSE de eventos persistidos

Autenticação: **operator**.

Eventos `status`, `text_delta`, `tool` e `done`, cada um com `id` igual à sequência. O cabeçalho `Last-Event-ID` tem precedência sobre `after`. Falhas após o início do fluxo chegam como evento `stream_error` com `message` e `code`. O fluxo termina após o evento `done`. Até 5 conexões por operador, com leases duráveis de 30 s renovados durante o fluxo; sem capacidade retorna 429 resource_limit. Leases abandonados são recuperados após o prazo, sem reiniciar a API.

Parâmetros: `run_id` (path, obrigatório); `after` (query, opcional); `Last-Event-ID` (header, opcional).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | text/event-stream |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 503 | ToolError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /runs/00000000-0000-4000-8000-000000000001/events`. Aplicar os cabeçalhos do perfil acima.

### POST `/runs/{run_id}/result`

Encerra a execução com resultado final

Autenticação: **worker + X-Run-Token**.

Com sucesso, `answer` deve coincidir com a concatenação dos `text_delta`. Benchmark bem-sucedido exige `experiment`. As chamadas declaradas devem corresponder ao histórico observado, e artefatos ao efeito da chamada. Erro no cliente pode coexistir com efeito confirmado. Duração não é comparada. Repetir o mesmo resultado é idempotente.

Parâmetros: `run_id` (path, obrigatório).

Entrada: `AgentResult`.

| HTTP | Saída |
| --- | --- |
| 200 | RunResponse |
| 401 | ToolError |
| 403 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /runs/00000000-0000-4000-8000-000000000001/result`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "status": "failed",
  "error_code": "adapter_error"
}
```

### GET `/artifacts/{artifact_id}`

Artefato gravado e recibo, para conferência pelo operador

Autenticação: **operator**.

Após conferir propriedade e concessões, valida ferramenta, payload, recibo, contexto do run, identificadores e hashes. Corrupção retorna 500 `invalid_response`. A leitura não exige lease ativo nem permissão de escrita.

Parâmetros: `artifact_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ArtifactResponse |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 422 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /artifacts/00000000-0000-4000-8000-000000000004`. Aplicar os cabeçalhos do perfil acima.

### POST `/tools/consultar_processo`

Metadados, inventário e cobertura da exportação

Autenticação: **worker + X-Run-Token**.

 Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `ToolContext`.

| HTTP | Saída |
| --- | --- |
| 200 | ProcessResult |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/consultar_processo`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1"
}
```

### POST `/tools/buscar_documentos`

Busca literal de trechos com fonte

Autenticação: **worker + X-Run-Token**.

Lista vazia não prova ausência no processo original. Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `SearchInput`.

| HTTP | Saída |
| --- | --- |
| 200 | SearchResult |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/buscar_documentos`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1",
  "query": "material",
  "limit": 5
}
```

### POST `/tools/ler_documento`

Lê documento inteiro ou páginas específicas

Autenticação: **worker + X-Run-Token**.

 Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `ReadInput`.

| HTTP | Saída |
| --- | --- |
| 200 | DocumentResult |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/ler_documento`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1",
  "document_id": "DOC-DEMO-001",
  "pages": [
    1
  ]
}
```

### POST `/tools/consultar_requisitos`

Checklist versionado do processo

Autenticação: **worker + X-Run-Token**.

 Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `ToolContext`.

| HTTP | Saída |
| --- | --- |
| 200 | RequirementsResult |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/consultar_requisitos`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1"
}
```

### POST `/tools/registrar_pendencia`

Registra pendência de requisito com evidências

Autenticação: **worker + X-Run-Token**.

Replay com a mesma `idempotency_key` e entrada devolve o recibo com `replayed: true`; entrada diferente recebe 409 `idempotency_conflict`. Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `PendencyInput`.

| HTTP | Saída |
| --- | --- |
| 200 | WriteReceipt |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/registrar_pendencia`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1",
  "idempotency_key": "exemplo-escrita-1",
  "content": "Texto exclusivamente sintético.",
  "evidence": [
    {
      "kind": "inventory",
      "process_id": "PROC-DEMO-001",
      "corpus_version": "synthetic-v1"
    }
  ],
  "evidence_note": "Limitação do inventário sintético.",
  "requirement_id": "REQ-DEMO-001"
}
```

### POST `/tools/salvar_minuta`

Persiste minuta fundamentada e devolve recibo

Autenticação: **worker + X-Run-Token**.

Mesma regra de idempotência de `registrar_pendencia`. Teto de 1.000 requisições físicas atribuíveis à lease por run, incluindo erros e retries. Excesso retorna 429 resource_limit, retryable false, antes do corpo/efeito; recusas permanecem auditadas.

Parâmetros: `X-Tool-Call-Id` (header, opcional).

Entrada: `WriteInput`.

| HTTP | Saída |
| --- | --- |
| 200 | WriteReceipt |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 429 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /tools/salvar_minuta`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "checklist-v1",
  "idempotency_key": "exemplo-escrita-1",
  "content": "Texto exclusivamente sintético.",
  "evidence": [
    {
      "kind": "inventory",
      "process_id": "PROC-DEMO-001",
      "corpus_version": "synthetic-v1"
    }
  ],
  "evidence_note": "Limitação do inventário sintético."
}
```

### POST `/experiments`

Registra a primeira revisão do ExperimentRun do run reservado

Autenticação: **worker + X-Run-Token**.

Somente o worker com a reserva do run de benchmark. `parameters.revision` ausente vira 1; outro valor retorna 409. Reenvio idêntico é idempotente, inclusive após o encerramento; conteúdo diferente retorna 409 idempotency_conflict. Contexto, tarefa e executor devem ser os da reserva, e `tool_calls` o histórico observado. Registro não comprova sucesso: `verified_success` e `evaluator` ficam nulos.

Parâmetros: nenhum.

Entrada: `ExperimentRun`.

| HTTP | Saída |
| --- | --- |
| 200 | ExperimentRun |
| 401 | ToolError |
| 403 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `POST /experiments`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "demo-v1",
  "task_id": "DEV-001",
  "split": "development",
  "executor": "langgraph",
  "repetition": 1,
  "code_commit": "0000000",
  "harness_version": "0.2",
  "adapter_version": "langgraph-0.1",
  "model": "openai/gpt-4o-mini",
  "endpoint_id": "openrouter",
  "prompt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "parameters": {
    "level": "chained",
    "revision": 1
  },
  "started_at": "2026-11-21T12:00:00Z",
  "latency_ms": 1200.0,
  "tool_calls": [],
  "agent_declared_success": true,
  "persisted_artifact_ids": [],
  "verified_success": null,
  "evaluator": null
}
```

### GET `/experiments/{run_id}`

Relê a revisão atual do ExperimentRun

Autenticação: **operator ou worker do mesmo executor**.

Operador dono do run ou worker do mesmo executor com concessão do processo. Run sem registro ou fora do escopo retorna 404 not_found.

Parâmetros: `run_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ExperimentRun |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 503 | ToolError |
| 422 | HTTPValidationError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /experiments/00000000-0000-4000-8000-000000000001`. Aplicar os cabeçalhos do perfil acima.

### PUT `/experiments/{run_id}`

Acrescenta revisão sequencial ao ExperimentRun

Autenticação: **worker + X-Run-Token**.

Somente o worker com a reserva ativa. A revisão deve ser a atual + 1 e não pode alterar identidade, protocolo, orçamento nem avaliação externa, nem reduzir latência, tokens ou chamadas já registradas: 409 idempotency_conflict. Caminho diferente do corpo retorna 422. Run encerrado só aceita o reenvio idêntico.

Parâmetros: `run_id` (path, obrigatório).

Entrada: `ExperimentRun`.

| HTTP | Saída |
| --- | --- |
| 200 | ExperimentRun |
| 401 | ToolError |
| 403 | ToolError |
| 409 | ToolError |
| 422 | ToolError |
| 500 | ToolError |
| 503 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `PUT /experiments/00000000-0000-4000-8000-000000000001`. Aplicar os cabeçalhos do perfil acima.

```json
{
  "run_id": "00000000-0000-4000-8000-000000000001",
  "process_id": "PROC-DEMO-001",
  "corpus_version": "synthetic-v1",
  "requirements_version": "demo-v1",
  "task_id": "DEV-001",
  "split": "development",
  "executor": "langgraph",
  "repetition": 1,
  "code_commit": "0000000",
  "harness_version": "0.2",
  "adapter_version": "langgraph-0.1",
  "model": "openai/gpt-4o-mini",
  "endpoint_id": "openrouter",
  "prompt_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "parameters": {
    "level": "chained",
    "revision": 2
  },
  "started_at": "2026-11-21T12:00:00Z",
  "latency_ms": 1500.0,
  "tool_calls": [],
  "agent_declared_success": true,
  "persisted_artifact_ids": [],
  "verified_success": null,
  "evaluator": null
}
```

### GET `/experiments/{run_id}/revisions`

Histórico de revisões do ExperimentRun

Autenticação: **operator ou worker do mesmo executor**.

Mesmo escopo de leitura de `GET /experiments/{run_id}`. Run autorizado sem registro retorna lista vazia.

Parâmetros: `run_id` (path, obrigatório).

Entrada: sem corpo JSON exigido.

| HTTP | Saída |
| --- | --- |
| 200 | ExperimentRun[] |
| 401 | ToolError |
| 403 | ToolError |
| 404 | ToolError |
| 503 | ToolError |
| 422 | HTTPValidationError |
| 500 | ToolError |
| 413 | ToolError |
| 405 | ToolError |

Exemplo de requisição: `GET /experiments/00000000-0000-4000-8000-000000000001/revisions`. Aplicar os cabeçalhos do perfil acima.

## Jornadas, streaming e transporte

Chat: consultar processos/capacidades, criar conversa, enviar mensagem, acompanhar run/SSE. Cada conversa fixa executor e escopo. Mensagem/run/evento inicial são atômicos; só uma execução ativa por conversa. A próxima pergunta recebe histórico de runs concluídos com sucesso, sem parciais de falhas.

Worker: claim, executar tools/eventos com reserva, heartbeat periódico, resultado. O exemplo `AgentResult` acima encerra com falha; benchmark com sucesso exige `experiment` completo e coerente. Resposta final deve coincidir com deltas quando publicados; sem deltas, resposta final única é permitida.

Busca fornece chunks/evidências para leitura/escrita; checklist fornece `requirement_id` para pendência; recibo fornece ID para GET de artefato/resultado experimental. Não há cadeia fixa obrigatória imposta às seis tools. Leitura parcial não prova completude do arquivo original. Minuta não exige checklist nem pendência.

SSE: `Last-Event-ID` prevalece sobre `after`; IDs são sequências crescentes. Eventos: `status`, `text_delta`, `tool`, `done`; erro de transporte/aplicação depois da abertura: `stream_error`. Comentários heartbeat não são eventos persistidos. Exemplo sintético:

```text
id: 3
event: text_delta
data: {"text":"Resposta sintética."}

id: 4
event: done
data: {"status":"succeeded"}

```

Após interrupção, consultar snapshot (`partial_answer`, `last_event_id`) e retomar após o cursor. Não contar eventos SSE como tentativas físicas. Leases abandonadas são recuperadas por TTL; isso não prova fechamento imediato de socket em processo congelado.

O proxy Next usa timeout de 20 s para operação inicial/leitura de corpo e 30 s de inatividade do stream, configurados por `BACKEND_PROXY_TIMEOUT_SECONDS` e `BACKEND_PROXY_IDLE_TIMEOUT_SECONDS`. Backend e proxy limitam corpo a 1 MiB. Nginx declara `client_max_body_size 1m` e leitura do upstream de 360 s. Não converter esses prazos em orçamento de inferência.

Erros próprios do proxy incluem `request_timeout`, `proxy_unavailable`, `upstream_timeout`, `upstream_unavailable`, além de `payload_too_large`. Não são automaticamente códigos de `ToolError` do backend. Nginx/Compose não foram homologados em execução; respostas da infraestrutura não são garantidas pelo schema da API. [Operação I3](../04-operacoes/validacao-i3.md).

## Compatibilidade e verificação

Clientes síncrono/assíncrono preservam corpo/ID em retry, validam resposta antes de aceitá-la e não repetem sucesso inválido. Campos novos de capabilities e causas terminais exigem revisão dos consumidores com enum/schema fechado. Catálogo contém descrições e omite contexto privilegiado; entrega efetiva ao modelo depende do adaptador real.

```powershell
uv run --locked python -m scripts.export_openapi --check
uv run --locked python -m scripts.validate_api_docs
uv run --locked python -m scripts.validate_repository
uv run --locked python -m pytest tests/backend/test_openapi.py tests/integration/test_i1.py
```

A validação dos exemplos comprova estrutura, não existência de recurso ou autorização. Os aceites HTTP/SQLite e limites da integração estão no [índice de estado](../04-operacoes/backend-estado-atual.md). Metodologia, Documentos, Hermes, LangGraph e Infra devem revisar seus consumidores antes da liberação conjunta.

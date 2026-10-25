# Contratos v0.2 — backend, tools e agentes

Fontes executáveis: [models.py](models.py) e [execution.py](execution.py).
A API publica OpenAPI em `/openapi.json` e documentação em `/docs`.
Pydantic rejeita campos extras e entradas inválidas sem ecoar seu conteúdo.

## Compatibilidade e revisão conjunta

v0.2 exige autenticação e execução reservada nas seis tools. Consumidores
v0.1 que enviavam um UUID arbitrário devem criar/reservar uma execução.
`ToolClient` e `AsyncToolClient` injetam o contexto autenticado e rejeitam
tentativas de alterá-lo. O protocolo `AgentAdapter` passa a oferecer
`stream(ClaimedRun, AsyncToolClient)`.

`ProcessResult` acrescenta inventário; `ReadInput` admite páginas opcionais.
`PendencyInput` acrescenta `requirement_id`. Escritas exigem ao menos uma
referência de chunk ou inventário. O contrato `ExperimentRun` v0.1 é
preservado dentro do envelope v0.2 para os consumidores de avaliação.

As equipes Backend, Documentos, Hermes, LangGraph, Metodologia e Infra devem
revisar essas mudanças antes de integrar suas entregas. Consulte
[operação do chat](../docs/04-operacoes/chat.md) para migrações e configuração.

## Autenticação e contexto

Operadores usam `Authorization: Bearer TOKEN_OPERADOR` para criar e
acompanhar suas conversas, execuções e artefatos. Workers usam um token
próprio, associado ao executor e a concessões explícitas por processo/corpus.

`POST /runs/claim` devolve `ClaimedRun`, incluindo `run_token`. Tools,
heartbeat, publicação de eventos e resultado exigem adicionalmente
`X-Run-Token`. O modelo não recebe poder de escolher usuário, execução ou
permissões. O cliente das tools associa o contexto antes de enviar HTTP.

`ToolContext` contém `run_id`, `process_id`, `corpus_version` e
`requirements_version`. Todos devem coincidir com a execução reservada.
Cada operação confere as concessões atuais do worker e do proprietário.
Escritas também exigem `can_write` nos dois perfis.

## Conversas e execuções

| Rota | Entrada e resultado |
| --- | --- |
| `GET /processos` | Processos/corpora autorizados ao operador. |
| `GET /capabilities` | Perfil e disponibilidade dos executores. |
| `POST /conversations` | Processo, corpus, requisitos e executor; retorna conversa. |
| `GET /conversations` | Até 100 conversas mais recentes do operador. |
| `GET /conversations/{id}` | Mensagens e execuções da conversa. |
| `POST /conversations/{id}/messages` | `content`, `idempotency_key`; retorna execução com HTTP 202. |
| `POST /runs` | Escopo, executor, `task`, `task_id`, `split`, `repetition`, chave; HTTP 202. |
| `GET /runs/{id}` | Estado, resultado, texto parcial e cursor consistente. |
| `POST /runs/claim` | Executor e `run_id` opcional; retorna reserva ou 204 sem tarefa. |
| `POST /runs/{id}/heartbeat` | Renova a reserva ativa. |
| `POST /runs/{id}/events` | Publica um `AgentEvent` idempotente. |
| `GET /runs/{id}/events` | SSE autorizado ao proprietário. |
| `POST /runs/{id}/result` | Encerra com `AgentResult`, de forma idempotente. |
| `GET /artifacts/{id}` | Conteúdo e recibo para conferência pelo proprietário. |

Uma conversa fixa processo, corpus, requisitos e executor. Cada pergunta
gera uma execução. A criação da pergunta e do run é atômica, com uma
execução ativa por conversa. Chaves de envio são únicas por operador:
entrada idêntica recupera o mesmo run; entrada diferente gera 409.

O worker recebe um snapshot de mensagens concluídas e da pergunta atual.
Falhas e parciais são excluídos do contexto seguinte. Contexto excessivo
retorna `context_limit`; não há truncamento ou resumo silencioso.

Estados: `queued`, `running`, `succeeded`, `failed`, `timed_out`.
A reserva padrão dura 60 segundos e recebe heartbeat a cada 15 segundos.
O orçamento total padrão é 300 segundos, configurável. A expiração é
verificada ao consultar/reservar tarefas e durante o streaming.
Uma execução interrompida não é reexecutada automaticamente.

Chat tem `kind=chat`; benchmark tem `kind=benchmark` e histórico isolado.
`ExperimentRun` é obrigatório para concluir um benchmark com sucesso.
Seus IDs, executor, tarefa e versões devem coincidir com a execução;
artefatos declarados devem existir. `verified_success` e `evaluator`
continuam nulos no resultado enviado pelo agente.

## Streaming e adaptação

Implementações de referência: [worker HTTP](../agents/worker.py),
[adaptador simulado](../agents/simulation.py) e
[clientes das tools](../agents/interface.py). Cada equipe conecta seu
runtime a esse protocolo, mantendo o catálogo comum e o contexto recebido.

O adaptador produz `AgentEvent` com `event_id` UUID, `kind` e `text`.
Tipos aceitos do worker: `status` e `text_delta`. O último item do adaptador
é `AgentResult` com estado, resposta, fontes, erro opcional e registro
experimental quando aplicável.

Cada evento é confirmado no banco antes de ser disponibilizado ao portal.
Reenvio de mesmo ID/conteúdo devolve a sequência original; conteúdo
diferente gera 409. O backend atribui sequências crescentes por execução.

SSE emite eventos `status`, `text_delta`, `tool` e `done`, com `id` numérico.
Use `Last-Event-ID` ou `?after=SEQUENCIA` para retomar. O snapshot do run
fornece texto parcial e cursor lidos sob a mesma trava. Depois de falha no
fluxo, recupere esse snapshot e reconecte.

A resposta final deve coincidir exatamente com os deltas publicados.
Um adaptador sem streaming pode enviar somente a resposta final; a UI não
simula tokens. O simulador incluído declara expressamente sua condição.
Somente o texto destinado à resposta e o progresso operacional são
publicados nesse canal.

## As seis tools

Todas usam `POST /tools/NOME` e devolvem o contexto autenticado.

| Nome | Entrada adicional | Resultado |
| --- | --- | --- |
| `consultar_processo` | Nenhuma. | Processo, cobertura e inventário documental. |
| `buscar_documentos` | `query` de 1–200 caracteres; `limit` de 1–20. | Chunks rastreáveis e aviso de cobertura. |
| `ler_documento` | `document_id`; `pages` opcional, positivas e únicas. | Texto das páginas solicitadas. |
| `consultar_requisitos` | Nenhuma. | Checklist da versão vinculada ao processo/corpus. |
| `registrar_pendencia` | `PendencyInput`. | `WriteReceipt` confirmado. |
| `salvar_minuta` | `WriteInput`. | `WriteReceipt` confirmado. |

A busca atual é substring literal, com filtros aplicados antes do limite.
Não há recuperação vetorial nesta entrega. Resultado vazio é 200 e não
comprova ausência no processo original. Checklist não importado gera 404.

Escritas recebem `idempotency_key`, `content`, `evidence` e `evidence_note`.
Pendência recebe também `requirement_id` do checklist versionado.
Referências são resolvidas pelo servidor:

```json
{"document_id":"DOC-DEMO-001","chunk_id":"ID_REAL_DO_CHUNK","page":1}
```

Para uma limitação do inventário, sem inventar documento ou página:

```json
{"kind":"inventory","process_id":"PROC-DEMO-001","corpus_version":"synthetic-v1"}
```

Unicidade: `(run_id, ferramenta, idempotency_key)`. Entrada idêntica devolve
o recibo original com `replayed=true`; entrada diferente gera 409.
Artefato e recibo são gravados na mesma transação. O servidor relê o recibo
após commit. Timeout após uma escrita deve ser resolvido repetindo a mesma
operação e chave, pois a confirmação pode ter se perdido.

`WriteReceipt` contém contexto, `artifact_id`, `persisted_at`, hash SHA-256
do conteúdo e `replayed`. Fonte existente não comprova sustentação
semântica: essa avaliação pertence ao protocolo metodológico.

## Erros seguros

| HTTP | Código |
| --- | --- |
| 401 | `unauthorized`: credencial ausente ou inválida. |
| 403 | `forbidden`: contexto, perfil ou concessão incompatível. |
| 404 | `not_found`: recurso autorizado inexistente. |
| 409 | `version_mismatch`, `idempotency_conflict` ou `conflict`. |
| 422 | `validation_error` ou `context_limit`. |
| 503 | `storage_unavailable` ou `executor_unavailable`. |

Respostas não incluem SQL, credenciais ou entradas rejeitadas.
`storage_unavailable` indica possibilidade de nova tentativa. Escritas e
eventos devem manter suas chaves originais ao repetir a chamada.


## Complementos locais — 24/10/2026

- Respostas tipadas de conversas, mensagens, runs, capacidades, heartbeat e
  artefatos estão em execution.py/models.py e aparecem no OpenAPI.
- ConversationInput recebe participant_id UUID opcional; permanece null no legado.
  GET /conversations aceita ?participant_id=UUID. O filtro não é autorização:
  acesso continua determinado pelo operador técnico e suas concessões.
- Snapshot de run inclui artifacts com artifact_id/tool. O operador consulta o
  conteúdo e recibo por GET /artifacts/{id}, inclusive após falha da execução.
- [Catálogo](catalog.py) exporta seis nomes, descrições e schemas dos argumentos
  para os modelos, sem campos de ToolContext. O cliente injeta o contexto.
- [Integração](../docs/04-operacoes/integracao-agentes.md) descreve a fábrica local
  e a homologação dos adaptadores; [TDD](../docs/02-arquitetura/backend-tdd.md)
  descreve a fronteira com RAG.

Essas adições exigem revisão de consumidores antes da integração compartilhada.
O marcador não é enviado no ClaimedRun nem determina permissões.

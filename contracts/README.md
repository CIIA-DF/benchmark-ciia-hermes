# Contratos v0.3 — backend, tools e agentes

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
| 409 | `version_mismatch`, `idempotency_conflict`, `conflict` ou `budget_exceeded`. |
| 422 | `validation_error` ou `context_limit`. |
| 503 | `storage_unavailable` ou `executor_unavailable`. |

Respostas não incluem SQL, credenciais ou entradas rejeitadas.
`storage_unavailable` indica possibilidade de nova tentativa. Escritas e
eventos devem manter suas chaves originais ao repetir a chamada.


## v0.3 — rastreio e orçamento das tools (25/10/2026)

Adições opcionais, descritas no [ADR 007](../docs/05-decisoes/007-rastreio-orcamento-tools.md):
cabeçalho `X-Tool-Call-Id` nas seis tools; código `budget_exceeded` (409) em `ToolError`;
evento SSE `tool` com `tool_call_id`, `status`, `code` e `replayed`; histórico de cada
tentativa no servidor; `AsyncToolClient.calls` para compor `ExperimentRun.tool_calls`.

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

## Endurecimento dos tipos — auditoria de 28/10/2026

Inteiros/booleanos dos modelos são estritos; métricas rejeitam valores não finitos.
`RunContext`, `HistoryMessage` e `TaskMetadata` têm chaves obrigatórias e fechadas,
mantendo dicionários para adaptadores. `HealthResponse` valida saúde e `ToolName`
limita nomes nos registros. Números como strings/booleanos e reservas sintéticas
incompletas deixam de ser aceitos. UUID/datetime preservam a representação JSON.

É endurecimento de validação com impacto em clientes antes tolerados. Backend,
Documentos, Hermes, LangGraph e Metodologia devem revisar antes da integração.
Correspondência semântica de `tool_calls` com histórico ainda é pendente:
tipagem não substitui autorização/conferência. Ver [auditoria](../docs/04-operacoes/auditoria-backend-2026-10-28.md).

## T0 — reserva durável e modelos de saída (28/10/2026)

O catálogo agora associa ToolSpec.input_model/description/output_model. Clientes
validam respostas de sucesso antes de devolver JSON ao adaptador; resposta inválida
é erro definitivo sem eco do conteúdo. Consumidores internos devem usar os campos
nomeados do catálogo em vez de desempacotar a tupla anterior.

Migração 0005 preserva a primeira ferramenta/entrada de cada chamada lógica.
Mesmo ID com entrada/tool diferente gera 409 idempotency_conflict; rollback não
libera ID ou orçamento. Corrigir entrada inválida exige ID novo. Retry da mesma
escrita mantém ID, corpo e idempotency_key. Atualizar consumidores e solicitar
revisão de Backend/Hermes/LangGraph antes de integrar. Ver [evidências T0](../docs/04-operacoes/validacao-t0-2026-10-28.md).

## T1 — consistência de consultar_processo

ProcessResult confere processo e versões contra o envelope e rejeita IDs duplicados
no inventário. A consulta valida também o escopo dos documentos armazenados.
Clientes comuns conferem contexto devolvido contra a execução da requisição.
Inconsistência interna gera 500 invalid_response (retryable=false), documentado
no OpenAPI desta tool. Consumidores que validam enums devem incorporar o código;
Backend, Documentos, Hermes e LangGraph precisam revisar antes de integrar.
Sucesso válido preserva o formato JSON, cobertura e nota. Ver [registro T1](../docs/04-operacoes/validacao-t1-2026-10-28.md).

## T2 — consistência de buscar_documentos

SearchResult rejeita chunks fora do contexto, IDs repetidos e mais de 20 itens.
Servidor/clientes comuns conferem também o limite específico da requisição e o
contexto devolvido. Payloads do índice precisam coincidir com suas chaves/texto.
Inconsistência retorna 500 invalid_response, sem retry automático nem eco.
Busca vazia continua 200, com cobertura e warning; não prova ausência documental.
Sem normalização Unicode nova. Revisão conjunta de Backend/Documentos/agentes
continua necessária. Ver [registro T2](../docs/04-operacoes/validacao-t2-2026-10-28.md).

## Correção T1-R — fronteira de processo

O processo armazenado é validado antes de acessar campos. Payload incompleto,
estrutura inválida, JSON null ou identidade incompatível geram 500 invalid_response
seguro. Linha ausente mantém 404; versão válida divergente mantém 409.
Nas tools, a falha é auditada depois da reserva durável T0-R2; mesma operação
pode ser recuperada após reparo administrativo, sem nova cobrança lógica.
Não há código/campo novo de contrato. [Fechamento T1-R](../docs/04-operacoes/validacao-t1-r.md).

## T3 — leitura de documento e páginas

DocumentResult confere processo/corpus e ordem das páginas. O servidor valida o
documento armazenado antes do filtro, confere o ID e devolve exatamente as páginas
pedidas em ordem documental crescente. Sem filtro, preserva todas as páginas.
Clientes conferem contexto da execução, documento e subconjunto da requisição.
Documento corrompido, inclusive JSON null ou páginas fora de ordem, gera 500
invalid_response seguro e auditado; documento/página ausente continua 404 e
entrada inválida 422. O hash é do documento completo, não do subconjunto.
Formato JSON mantido; revisão de Backend/Documentos/agentes necessária antes de
integrar. [Evidências e workflow T3](../docs/04-operacoes/validacao-t3.md).

## T4 — checklist versionado

RequirementsResult exige lista não vazia e IDs únicos. Servidor filtra por
processo/corpus/requirements_version e confere o ID do payload contra a chave
persistida; clientes comuns conferem o contexto completo da execução. Checklist
ausente mantém 404; payload inconsistente gera 500 invalid_response seguro e
auditado; banco indisponível mantém 503 transitório. JSON válido preservado;
OpenAPI explicita minItems=1. Importação administrativa imutável preservada.
items[].requirement_id alimenta registrar_pendencia.requirement_id no mesmo
escopo. Conteúdo/homologação continuam sob Metodologia; Backend, Documentos e
agentes devem revisar a compatibilidade antes de integrar. [Evidências e workflow T4](../docs/04-operacoes/validacao-t4.md).

## T5 — pendência e integridade do recibo

PendencyInput mantém o JSON. O requisito selecionado e o chunk referenciado são
validados contra armazenamento/escopo antes do efeito; inconsistência é 500
invalid_response seguro e auditado, enquanto referência ausente continua 422.
WriteReceipt.artifact_id agora é UUID e persisted_at exige fuso (AwareDatetime);
JSON continua string/date-time. Escritor comum confere payload canônico, hashes,
chaves, contexto e recibo na escrita, replay e releitura independente pós-commit.
Clientes comuns conferem contexto e hash do conteúdo de registrar_pendencia.

Mudanças compartilhadas afetam salvar_minuta (escritor/recibo), GET de artefatos
(schema) e resultado do worker (fontes; 500 documentado). T6/A7 continuam separados.
IDs arbitrários, timestamps sem fuso ou registros inconsistentes podem ser
recusados; sem migração/reparo automático. Backend, Documentos, Hermes/LangGraph e
Metodologia devem revisar antes de integrar. Falha pós-commit pode deixar efeito
confirmado: retry conserva IDs/corpo. [Workflow, respostas e limites T5](../docs/04-operacoes/validacao-t5.md).

## T6 — conferência de salvar_minuta no cliente

Clientes síncrono/assíncrono agora conferem contexto e content_sha256 do recibo de
salvar_minuta contra execução e conteúdo enviado. As duas escritas usam o modelo
de entrada do catálogo na mesma checagem, sem duplicar o escritor ou a regra de
hash. Resposta válida preserva JSON; 200 inconsistente é ToolCallError definitivo,
sem eco nem retry automático. WriteInput/WriteReceipt e OpenAPI não mudaram nesta
rodada. Minuta não exige requirement_id, checklist cadastrado ou pendência prévia.
Backend, Documentos e agentes devem revisar consumo antes de integrar; Metodologia
continua responsável por qualidade semântica. [Workflow e evidências T6](../docs/04-operacoes/validacao-t6.md).

## F0 — tentativa física e fases

Migração aditiva 0006 acrescenta physical_tool_attempts/physical_tool_phases.
PhysicalToolAttempt/PhysicalToolPhase tipam a leitura interna ToolTracking.history.
UUID físico é gerado por requisição no servidor, separado do ID lógico e de seu
orçamento. Efeito confirmado e resposta preparada são fases da mesma tentativa;
client_received permanece null. Legado não recebe backfill e tool_call_history
continua um ledger de compatibilidade de estágios, sem precisão física presumida.
Nenhum endpoint/schema público mudou. Backend, agentes e Metodologia devem revisar
antes de integrar; adoção ampla/exportação permanecem nos blocos próprios.
[ADR 008](../docs/05-decisoes/008-tentativas-fisicas-tools.md) e [evidências F0](../docs/04-operacoes/validacao-f0.md).

## F1 — consultar_processo com rastreamento físico

Integração de F0 verificada por HTTP/banco para processo e inventário. ToolContext,
ProcessResult e OpenAPI permanecem iguais. 200 com inventário vazio, 404 ausente,
409 de versão válida divergente, 500 seguro de metadados/inventário e 503 do banco
mantêm reservas e tentativas físicas coerentes. A leitura não cria fase de artefato;
client_received continua null. [Aceite e workflow F1](../docs/04-operacoes/validacao-f1.md).

## F2 — busca sem U+0000

SearchInput.query agora publica pattern `^[^\x00]+$`: NUL em qualquer posição é
422 validation_error antes da busca, sem remoção do caractere ou ampliação do termo.
Min/max de caracteres, limite, escape literal e SearchResult permanecem iguais.
OpenAPI e catálogo compartilham a restrição. Entrada recusada atribuível preserva
hash do corpo, reserva/orçamento e tentativa física F0; clientes recebem erro
recuperável, sem retry automático. Backend, Documentos e agentes devem revisar o
schema antes de integrar. [Workflow, respostas e evidências F2](../docs/04-operacoes/validacao-f2.md).

## F3 — leitura com rastreamento F0

Integração T3/F0 verificada por HTTP e banco. ReadInput/DocumentResult permanecem iguais.
Seleção respeita páginas exatas e ordem documental; sha256 continua do documento completo.
Cada requisição tem tentativa física própria, sem fase de artefato ou prova de recebimento.
Leitura parcial não comprova completude do arquivo original. [Aceite F3](../docs/04-operacoes/validacao-f3.md).

## F4 — checklist com rastreamento F0

Integração T4/F0 verificada por HTTP/banco. Modelos e OpenAPI preservados.
Checklist não vazio, IDs únicos e escopo versionado continuam obrigatórios.
Consulta registra fases de leitura; somente pendência válida confirma artefato.
Requisito estrangeiro permanece recusado. [Aceite F4](../docs/04-operacoes/validacao-f4.md).

## F5 — integridade reutilizável

validate_artifact recebe registro, ferramenta e contexto confiável do run; retorna ArtifactResponse tipado.
Escritor preserva validação da entrada exata, permissões, fontes, transações e replay.
execution.digest continua disponível; algoritmo canônico foi movido sem alteração.
GET permanece inalterado. A1 adotará a validação com autorização própria. [Aceite F5](../docs/04-operacoes/validacao-f5.md).

## F6 — minuta e fechamento F

Minuta reutiliza validate_artifact de F5 e rastreamento físico F0.
Jornada busca/leitura/escrita preserva contexto, fontes, conteúdo e hash sem exigir checklist ou pendência.
Clientes mantêm recusa definitiva de recibos adulterados. Nenhum contrato público mudou no F6.
[Matriz e evidências de fechamento F](../docs/04-operacoes/validacao-f6.md).

## A0 — fronteira HTTP

ToolError acrescenta os códigos internal_error, http_error, method_not_allowed e payload_too_large.
Validação de saída produz 500 invalid_response; entrada mantém 422 validation_error.
Corpo acima de 1 MiB produz 413, inclusive com partes ou Content-Length menor que o recebido.
401 acrescenta challenge Bearer; 405 preserva Allow; respostas privadas usam no-store.
SSE aberto mantém status e comunica falha por stream_error.
Consumidores comuns preservam o envelope tipado; revisar novos códigos e limites antes de integrar.
[Evidências e workflow A0](../docs/04-operacoes/validacao-a0.md).

## A1 — integridade no GET de artefatos

GET /artifacts/{id} reutiliza validate_artifact após conferir propriedade e grants.
Valida contexto do run, ferramenta, payload, recibo, IDs, hashes e chave; corrupção acessível retorna 500 invalid_response seguro.
ArtifactResponse e seu JSON permanecem iguais. Leitura não exige can_write nem lease ativo.
Portal e consumidores HTTP devem tratar a recusa de registros inconsistentes.
[Workflow, catálogo e evidências A1](../docs/04-operacoes/validacao-a1.md).

## A2 — reconciliação do resultado experimental

POST /runs/{id}/result exige IDs lógicos únicos e correspondência com reservas e histórico atribuível ao run quando experiment é enviado.
Ferramenta, sucesso declarado e artefato precisam de evidência compatível. persisted_artifact_ids corresponde aos IDs declarados nas chamadas, sem duplicações.
Erro no cliente pode coexistir com resposta 200 ou efeito confirmado; ausência de resposta não é execução inexistente. Não há igualdade de duração nem certificação de recebimento.
Declaração sem identidade atribuída é recusada; failed sem experiment continua disponível para falhas de adaptador/transporte.
Modelos/códigos permanecem iguais; divergências semânticas novas retornam 422 validation_error. Corrupção persistida retorna 500 invalid_response.
A pendência histórica de correspondência semântica é tratada para novos envios; não há revalidação retroativa de resultados terminais.
Backend, adaptadores e Metodologia devem revisar antes de integrar. [Workflow, respostas e evidências A2](../docs/04-operacoes/validacao-a2.md).

## A3 — quota queued na criação de benchmark

POST /runs aceita por padrão até 20 runs queued por operador, contando todos os seus escopos/kinds. RUN_MAX_QUEUED_PER_OPERATOR é inteiro positivo, padrão 20.
Replay idêntico precede quota; chave com outra entrada mantém 409. Nova criação sem capacidade retorna 429 resource_limit com retryable true e no-store, sem efeito persistido.
Não há Retry-After ou reenvio automático: liberação depende do consumo da fila. Preservar chave/corpo ao repetir.
ErrorCode acrescenta resource_limit; schemas de entrada/saída mantêm campos. Consumidores devem tratar o novo código/status antes da integração.
Mensagens queued entram na contagem; a quota também é aplicada ao envio de mensagens desde A4.
[Workflow, respostas e evidências A3](../docs/04-operacoes/validacao-a3.md).

## A4 — APIs de conversas e quota comum

POST /conversations/{id}/messages aplica a mesma quota de queued do POST /runs, sob a trava do operador e antes de gravar mensagem/run/evento.
Mantém replay antes da quota, conflito de entrada/chave e uma execução ativa por conversa. Sem vaga retorna 429 resource_limit, retryable true, sem efeito parcial.
POST/GET da coleção e GET do detalhe preservam contexto, grants, propriedade, filtro e modelos. Não houve paginação nova ou mudança de memória.
Portal/consumidores de mensagens devem tratar 429 e conservar chave/entrada ao repetir. Código/DTOs permanecem os de A3.
[Workflow, matriz por endpoint e evidências A4](../docs/04-operacoes/validacao-a4.md).

## A5 — expiração da fila

Queued vence após 300 s desde created_at, configurável por RUN_QUEUE_TIMEOUT_SECONDS positivo. A manutenção passiva é acionada por GET, criação e claim; a quota/claim revalidam o prazo sob suas travas.
Snapshot retorna timed_out com result.error_code queue_timeout. Done de fila inclui error_code queue_timeout. Histórico, parciais e artefatos são preservados; não há reabertura por replay.
StoredResult aceita a causa nova; AgentResult do worker continua sem permissão de enviá-la. Consumidores de enum fechado devem atualizar antes da integração.
Portal recebeu o rótulo da causa; erro não significa desconexão comprovada de worker/LLM.
[Workflow, configuração, respostas e testes A5](../docs/04-operacoes/validacao-a5.md).

## A6 — presença observada no claim

ClaimedRun e 204 permanecem iguais. Polling autorizado grava presença durável, inclusive sem tarefa; isso não comprova inferência.
Migração 0007 é aditiva, sem backfill. [Workflow e evidências A6](../docs/04-operacoes/validacao-a6.md).

## A7 — presença no heartbeat

HeartbeatResponse mantém status running. Renovação de presença e lease é atômica e exige identidade atual compatível.
Sem novo campo público. [Workflow e evidências A7](../docs/04-operacoes/validacao-a7.md).

## A8 — teto de eventos

20.000 eventos por run, incluindo servidor/tools/done; última vaga terminal. Excesso retorna 429 resource_limit, retryable false, e resultado failed/event_limit.
StoredResult acrescenta event_limit; AgentResult do worker não aceita essa causa. Replays aceitos não consomem vaga enquanto ativo.
Portal atualizado; consumidores devem incorporar a causa e consultar snapshot após limite. Histórico anterior não é apagado.
[Workflow, exceção legada e evidências A8](../docs/04-operacoes/validacao-a8.md).

## A9 — admissão SSE

GET /runs/{id}/events permite até cinco conexões por operador entre processos, com leases duráveis de 30 s.
Excesso retorna 429 resource_limit, retryable true, antes de abrir. Cursor, reconexão e stream_error permanecem iguais.
Sem novo cabeçalho público. [Workflow, respostas e limitações A9](../docs/04-operacoes/validacao-a9.md).

## A10 — configuração e presença

ExecutorCapability mantém available como configuração habilitada e acrescenta enabled, worker_recent, last_seen_at, model e configuration_known.
Presença recente exige observação até 60 s e escopo compartilhado atual. Modelo remoto null e configuration_known false não são inferidos do ambiente da API.
Portal atualizado; consumidores com schemas fechados devem incorporar os campos. [Evidências A10](../docs/04-operacoes/validacao-a10.md).

## A12 — identidade na listagem

GET /processos mantém list[Process], escopo e vazio 200. Agora valida a identidade do JSON contra a linha concedida; divergência retorna 500 invalid_response seguro.
Sem campo novo ou mudança no corpus. [Evidências A12](../docs/04-operacoes/validacao-a12.md).

## A13 — quota física e executor

As seis tools admitem até 1.000 requisições físicas atribuíveis à lease por run, incluindo entradas inválidas e retries.
Excesso retorna 429 resource_limit, retryable false, sem executar. Recusas continuam auditadas; o número de registros pode superar 1.000.
Mantém ID lógico, contratos e regras F; executor incompatível recebe 403. [Workflow e catálogo A13](../docs/04-operacoes/validacao-a13.md).

## Fechamento local do bloco A

A0–A13 verificados por suíte completa de 390 testes em SQLite após os aceites individuais.
[Workflow, campos/códigos públicos, limites e pendências](../docs/04-operacoes/validacao-a-fechamento.md).
PostgreSQL e revisão das equipes afetadas permanecem pendentes para homologação global. Sem publicação ou aceite automático de integração.

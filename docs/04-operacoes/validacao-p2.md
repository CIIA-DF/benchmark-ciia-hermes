# Validação P2 — pendências restantes da auditoria de 30/10/2026

Fase 2 do [plano por blocos](../02-arquitetura/backend-plano-blocos.md), aberta em 25/11/2026 na worktree `team/backend`. Continua a [validação P](validacao-p.md). Ordem dos sub-blocos: P8, P7, P10 e P9. Cada um tem teste que falha antes e passa depois, e a suíte completa em SQLite e PostgreSQL roda ao fechar a fase.

## P8 — Isolamento no PostgreSQL

**Problema.** Com `TEST_DATABASE_URL`, todos os testes compartilhavam o mesmo schema. O P6 contornou os conflitos com IDs únicos e desligou duas verificações:

- `test_e_export.py`: a exportação do banco inteiro era pulada, porque a corrupção proposital de outros testes (A1) a interrompia;
- `test_i2.py::test_bootstrap_race_creates_one_identity_and_one_event`: com `local-operator` já presente, a corrida esperava 0 eventos e deixava de ser exercitada.

**Mudança, só em testes.** A fixture `engine` (`tests/conftest.py`) cria um schema `t_<hex>` por teste e migra até o head. Depois remove o schema com `DROP SCHEMA … CASCADE`, com `lock_timeout` de 10 s. O `search_path` vai na URL (`options=-csearch_path=…`), porque vários testes recriam engines a partir de `engine.url` e `test_a9` passa a URL a um subprocesso. `make_engine` passa a aceitar `URL` na anotação de tipo, sem mudança de comportamento. As duas verificações voltam a ser incondicionais. Em SQLite nada muda: continua um banco temporário por teste.

| Verificação | Resultado |
| --- | --- |
| Fixture antiga com as asserções restauradas, num PostgreSQL 17 novo, `test_a1`, `test_i2` e `test_e_export` | `test_bootstrap_race_creates_one_identity_and_one_event` falha: o `local-operator` criado por outro teste já existe |
| Fixture nova, no mesmo banco com os resíduos da rodada anterior, `test_a1`, `test_i2`, `test_e_export`, `test_a9`, `test_ready` e `tests/integration/test_roundtrip.py` | 57 aprovados, 206,41 s; nenhum schema `t_*` sobrou |
| Mesma seleção em SQLite | 57 aprovados |

**Limites.** O custo de migrar até o head em cada teste no PostgreSQL será medido na suíte completa do fechamento da fase. A fixture exige permissão `CREATE` no banco de testes; na CI o usuário do serviço `postgres` tem essa permissão. `test_a9` (filtro `PREEXISTING`) e `test_ready` (restauração de `alembic_version`) mantêm proteções que ficaram redundantes, mas são inofensivas.

## P7 — Cobertura do P3

**Problema.** O P3 recusou U+0000 em `Text`, `AgentEvent.text` e `AgentResult.answer`, mas campos de texto livre gravados pelo worker continuavam aceitando o caractere: nomes e valores de texto de `ExperimentRun.parameters`, `ExperimentRun.evaluator` e `HistoryMessage.content`. Um `parameters={"nota": "x<U+0000>"}` passava em `/experiments` com 200 e ia para o JSON gravado.

**Mudança, de contrato.** Novos aliases em `contracts/models.py`: `NulFree` (sem U+0000, aceita vazio e espaços) e `ParameterName` (1 a 120 caracteres, sem U+0000). `Text` não serve aqui: exige ao menos um caractere. Valem para os nomes e valores de texto de `parameters`, para `evaluator` e para `HistoryMessage.content`. Os campos preenchidos só pelo servidor (`ToolError.message`, `PhysicalToolAttempt.method`/`code` e afins) não mudam. `catalog_version()` continua `f419b756…e2c`. OpenAPI regenerado. Registro em [contracts/README.md](../../contracts/README.md).

| Verificação | Resultado |
| --- | --- |
| `pytest tests/backend/test_p3_nul_text.py -k p7` sem a mudança | 5 falhas: os 4 casos de modelo aceitavam U+0000 e `/experiments` respondia 200 |
| `pytest tests/backend/test_p3_nul_text.py` com a mudança | 13 aprovados, inclusive vazio em `parameters` e em `HistoryMessage.content` |
| Regressões: `test_experiment_runs`, `test_compat`, `test_a2`, `test_e_export`, `test_chat_delivery`, `test_catalog_shared`, `test_openapi` e `tests/integration/test_adapter_protocol.py` | 74 aprovados em SQLite |
| `ruff check`, `ruff format --check`, `scripts.validate_api_docs` (26 operações), `scripts.export_openapi` | Sem erros |

**Limites.** Valores de texto de `parameters` continuam sem limite de tamanho, como antes. Adaptadores reais não foram exercitados.

## P10 — Item 1, perda de transporte

**Problema.** Se as 3 tentativas de uma tool falham antes do envio (`ConnectError`), o servidor nunca vê a chamada. O cliente comum a registrava em `tool_calls` como `error`; o `/result` recusava o registro com 422 (regra do A2: chamadas declaradas iguais às observadas), e o run de benchmark terminava `failed`, mesmo com o agente recuperado. Opção 3 da [validação P](validacao-p.md#item-1-opções-avaliadas-em-2211), escolhida pelo responsável em 25/11.

**Mudança no cliente comum e no registro experimental.**

- `ToolClient.call` e `AsyncToolClient.call` (`agents/interface.py`) separam a chamada lógica em `unobserved` quando nenhuma tentativa pode ter chegado ao servidor. Isso vale para todas as tentativas com `httpx.ConnectError`, `ConnectTimeout` ou `PoolTimeout`, e para falha ao montar a requisição. Qualquer outra situação conta como possivelmente observada: resposta HTTP, `ReadTimeout` ou cancelamento no meio do envio. Nesses casos a chamada continua em `calls`.
- `normalized()` (`agents/compat.py`) grava `parameters["unobserved_tool_calls"]` com a contagem, inclusive 0. A `RunBridge`, o `ExperimentSink` e o simulador usam a mesma regra. A constante `UNOBSERVED_PARAMETER` fica em `contracts/models.py`.
- O servidor (`services/backend/experiments.py`) exige inteiro não negativo e não decrescente entre revisões. Ele não consegue confirmar a contagem. `result_integrity.py` não muda: `tool_calls` continua igual ao histórico observado.

| Verificação | Resultado |
| --- | --- |
| `pytest tests/backend/test_p10_unobserved.py` sem a mudança | 11 falhas. O run com tool perdida termina `failed`; `/experiments` aceita contagem negativa, booleana, texto e fracionária; revisão pode reduzir a contagem |
| Mesmo arquivo com a mudança | 11 aprovados: separação nos dois clientes, `ReadTimeout` e queda seguida de resposta continuam observados, run recuperado `succeeded` com `unobserved_tool_calls=1`, recusas 422/409 |
| Regressões: `test_compat`, `test_experiment_runs`, `test_a2` (inclui `test_never_executed_is_rejected`, inalterado), `test_e_export`, `test_benchmark_batch`, `test_worker_polling` e `tests/integration` | Aprovados, código de saída 0 |
| `ruff check`, `ruff format --check` | Sem erros |

**Limites.** O aceite da Metodologia sobre como contar esses runs está pendente. A contagem é declarada pelo cliente e não é verificável no servidor. Na exportação JSONL v2, `parameters` só sai com `--include-content`; levar a contagem para `declared` fica para o bloco O. Adaptadores que montam `ExperimentRun` sem a `RunBridge` (LangGraph isolado, runner da Evaluation) precisam gravar `len(tools.unobserved)`. Hermes, LangGraph e Evaluation precisam ser avisados.

## P9a — Contador de caracteres parciais

**Problema.** Para conferir o limite de 100.000 caracteres, cada `POST /runs/{id}/events` com `text_delta` relia e concatenava todos os deltas anteriores (`ExecutionService.partial`). O custo crescia a cada evento, e o run inteiro ficava quadrático. Com deltas de 40 caracteres, como os do simulador, são até 2.500 eventos.

**Mudança.** A migração `0012` acrescenta `runs.partial_chars`, preenchido somando os deltas já gravados. `add_event` confere o limite pelo contador e o incrementa na mesma transação, sob a trava do run (`worker_run`, `FOR UPDATE`) que já protege `event_sequence`. O replay idempotente de um evento não soma de novo. `partial()` continua servindo a `GET /runs/{id}` e ao `/result`.

| Verificação | Resultado |
| --- | --- |
| Custo isolado de `partial()` (script temporário, mediana de 30 chamadas) | 1,2 ms com 10 deltas; 5,0 ms com 500; 16,4 ms com 2.500 |
| `scripts.measure_backend events --count 2500` (mediana por decil, ms por evento), antes | 16,7; 13,1; 17,9; 19,3; **266,8**; 18,6; 21,9; 22,4; **262,6**; 27,7 |
| Mesmo comando, depois | **186,1**; 11,8; 14,6; 14,1; 11,3; **241,0**; 12,4; 12,2; 15,0; **254,2** |
| `pytest test_p9_partial_chars.py test_ready.py test_p3_legacy_nul.py test_migrations.py` | 10 aprovados: limite exato em 100.000, replay sem contagem dupla, `status` fora da conta, preenchimento pela `0012` depois de downgrade/upgrade e head `0012` |

Os decis em negrito são picos de contenção da máquina, com outra suíte e outro projeto rodando. Eles aparecem nos dois casos e não acompanham o tamanho do run. Fora deles, o custo por evento sobe de 13 para 28 ms antes da mudança e fica entre 11 e 15 ms depois. A máquina não oferece medição limpa; o resultado vale como tendência, não como número de desempenho.

**Limites.** `GET /runs/{id}` ainda reconstrói o texto parcial a cada consulta, o que é proporcional ao run, mas não por evento. A `0012` não foi exercitada em PostgreSQL com dados; isso fica no bloco H.

## P9b — Claim sem travar a fila

**Problema.** `ExecutionService.claim` fazia `SELECT … FOR UPDATE SKIP LOCKED` sobre **todos** os runs na fila do executor, sem `LIMIT`, e conferia as concessões em Python. Enquanto a transação de um worker estava aberta, todos esses runs ficavam travados; outro worker pulava todos e recebia 204 com trabalho na fila. Runs pulados por falta de concessão também continuavam travados até o fim da transação.

**Mudança.** O claim lista os IDs dos candidatos sem trava, na mesma ordem (`created_at`). Depois trava um por vez com `FOR UPDATE SKIP LOCKED`, conferindo de novo `status = 'queued'`. Concessões, expiração da fila e reserva seguem como antes. Não há migração. No SQLite nada muda na prática: `BEGIN IMMEDIATE` já serializa as escritas.

| Verificação | Resultado |
| --- | --- |
| `tests/backend/test_p9_claim.py` no PostgreSQL 17 sem a mudança: worker A segura a transação depois de reservar; worker B pede claim com outro run na fila | Falha: B recebe `None` (204) |
| Mesmo teste com a mudança, PostgreSQL 17 novo, três rodadas | 3 de 3 aprovados (3,5 s, 8,0 s e 7,0 s); A e B recebem runs diferentes |
| Mesmo teste em SQLite | Aprovado; B espera a transação de A e depois reserva o outro run |
| `test_a3`, `test_a4`, `test_a5`, `test_a6`, `test_worker_polling`, `test_execution` e `test_p9_claim`, em SQLite | 53 aprovados, 283,88 s |
| `test_a5`, `test_a6` e `test_p9_claim` no PostgreSQL 17 | 15 aprovados |

**Limites.** O filtro de concessões continua em Python, um candidato por vez. Com muitos runs sem concessão na fila, o claim ainda percorre todos. A quota de 20 runs por operador limita isso. Levar o filtro para SQL exigiria desnormalizar `process_id`/`corpus_version` em `runs`, o que não foi feito. Uma primeira execução do comando de comparação passou de 300 s com a máquina carregada; as três repetições cronometradas acima não se repetiram nisso.

## P9c — Laço SSE com menos escritas

**Problema.** A cada tick de 200 ms, o laço de `GET /runs/{id}/events` chamava `renew_stream`, uma transação de escrita que trava a linha do operador (a mesma trava de `POST /runs`). Também chamava `read_events`, que rodava `expire()`, outra transação de escrita. Eram cerca de 10 transações de escrita por segundo por stream, com até 5 streams por operador.

**Mudança.** A autenticação (`actor`) e o escopo (`owned_run` em `read_events`) continuam conferidos a cada tick. A revogação e a perda de concessão encerram o fluxo como antes. A renovação da lease passa a ocorrer a cada `SSE_RENEW_SECONDS` (7,5 s, um quarto do TTL de 30 s). `expire()` sai de `read_events`, que fica só leitura, e roda no laço a cada `SSE_MAINTENANCE_SECONDS` (2 s), inclusive no primeiro tick. Assim a expiração da fila e do worker continua visível para quem só acompanha pelo stream.

| Verificação | Resultado |
| --- | --- |
| `tests/backend/test_p9_sse.py` sem a mudança: transações de escrita de um stream parado em 3 s | 28; o teste exige no máximo 4 |
| Mesmo teste com a mudança | Aprovado |
| `test_p9_sse`, `test_a9` (cota, recuperação, revogação, corrida entre processos), `test_a0` (erros antes/depois da abertura), `test_a5`, `test_run_snapshots`, `test_chat_delivery` e `tests/integration/test_i3.py`, em SQLite | 61 aprovados |
| `test_p9_sse`, `test_a9` e `test_run_snapshots` no PostgreSQL 17 | 12 aprovados |

**Limites.** Com a renovação a cada 7,5 s, uma lease removida por fora (o que hoje só o próprio fechamento faz) é percebida em até 7,5 s, e não em 200 ms. O polling de 200 ms continua para ler eventos; trocar por notificação do banco não faz parte desta entrega.

## P9d — Auditoria antes da autenticação

Não tratado. Hoje `app.py` registra a tentativa física de qualquer requisição a `/tools/<tool>` antes de autenticar. Isso é intencional desde o F0 ("recusas permanecem auditadas") e custa cerca de 4 escritas por requisição sem credencial. Mudar altera a semântica de auditoria do F0 e precisa de decisão do responsável.

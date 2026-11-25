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

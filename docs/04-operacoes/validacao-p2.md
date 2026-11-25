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

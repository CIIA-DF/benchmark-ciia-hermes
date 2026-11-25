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

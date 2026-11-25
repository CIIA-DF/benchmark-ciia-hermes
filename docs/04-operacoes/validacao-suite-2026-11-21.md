# Suíte completa — SQLite e PostgreSQL 17 (21/11/2026)

Worktree `team/backend`, HEAD `b266a31`, com as alterações locais sem commit do port J e da revisão de código ([validação J](validacao-j.md)). Por causa da memória da máquina (8 GB), a suíte rodou em seis grupos sequenciais: `test_a*`, `test_f*`, `test_t*`, o restante de `tests/backend`, `tests/integration` e `tests/documents`. Os logs e relatórios JUnit ficaram no diretório temporário da sessão, fora do repositório.

## Resultado

| Grupo | SQLite (banco temporário por teste) | PostgreSQL 17 (banco compartilhado `ciia-h-postgres17`) |
| --- | --- | --- |
| `test_a*` | 122 aprovados | 110 aprovados, 12 falhas |
| `test_f*` | 52 aprovados (290 s) | 52 aprovados (118 s) |
| `test_t*` | 150 aprovados (882 s) | 150 aprovados (371 s) |
| restante de `tests/backend` | 126 aprovados (435 s) | 122 aprovados, 4 falhas (213 s) |
| `tests/integration` (inclui o proxy Node do I3) | 57 aprovados (97 s) | 57 aprovados (58 s) |
| `tests/documents` | 7 aprovados | 7 aprovados |
| **Total** | **514 aprovados, 0 falhas, 0 pulados** | **498 aprovados, 16 falhas** |

Depois, cada uma das 16 falhas rodou sozinha num banco PostgreSQL novo e vazio (`ciia_fresh_N`, criado e apagado no mesmo container): 15 passaram e 1 falhou.

## Falhas no PostgreSQL

**Defeitos de teste corrigidos nesta rodada**

O primeiro defeito apareceu no teste rápido de conexão (`test_ready.py` + `test_migrations.py`), antes da suíte. Os outros dois estão entre as 16 falhas.

| Teste | Causa | Correção |
| --- | --- | --- |
| `test_ready.py::test_ready_fails_while_schema_is_behind_but_health_stays_up` (escrito em 21/11) | Mudava `alembic_version` para `0009` e não restaurava. No PostgreSQL compartilhado, isso fez a migração seguinte tentar recriar `experiment_runs` (`DuplicateTable`) | O teste restaura a revisão original no `finally`. A revisão do banco de teste foi corrigida à mão para `0010` (as tabelas da 0010 existiam) |
| `test_a9.py::test_separate_processes_cannot_overbook_last_slot` (já existia em `0c8b6ac`) | Passava `str(engine.url)` ao subprocesso. O SQLAlchemy troca a senha por `***` nesse texto, e a autenticação no PostgreSQL falha; o SQLite não tem senha | A URL completa (`render_as_string(hide_password=False)`) vai por variável de ambiente, não pela linha de comando |
| `test_i2.py::test_bootstrap_warns_when_environment_token_differs` (escrito em 21/11) | Supunha que `local-operator` ainda não existia | O teste fixa o token gravado antes do bootstrap |

Os três passam agora em SQLite, em PostgreSQL vazio e no PostgreSQL compartilhado.

**Isolamento de testes no banco compartilhado (não corrigido)**

Estas 14 falhas passam num banco vazio e falham no banco reaproveitado. O `tests/conftest.py` declara que IDs únicos permitem rodar contra PostgreSQL sem apagar dados, mas estes testes contam linhas globais ou usam IDs fixos:

- `test_a0::test_tool_oversize_is_recorded_without_logical_binding`, `test_a6::test_invalid_poll_and_stale_authenticated_role_do_not_record_presence` e os três casos de `test_a7::test_stale_identity_cannot_refresh_lease_or_presence`: `MultipleResultsFound` ou contagens globais.
- `test_a9`: `test_abandoned_lease_recovery_and_expired_stream_cannot_resurrect`, os três casos de `test_live_http_stream_releases_on_completion_disconnect_or_revocation` e `test_send_failure_before_body_releases_even_without_iterating`: contam todas as leases de stream (por exemplo, 14 em vez de 1).
- `test_a12::test_process_listing_preserves_scope_typed_output_and_valid_empty`: o processo fixo `PRIVATE-A12-ungranted` já existe.
- `test_e_export::test_scope_kinds_empty_export_and_deterministic_output`: exporta o banco inteiro e encontra um artefato com recibo `null`, deixado de propósito por `test_a1` (o teste de artefato corrompido).
- `test_i2::test_bootstrap_race_creates_one_identity_and_one_event` e `test_i2::test_audit_failure_rolls_back_credentials_grants_and_profile[rotate]`: contam eventos de `local-operator` e `rollback-profile`, que se acumulam entre rodadas.

Nenhuma dessas falhas indicou defeito do backend: o mesmo teste passa num banco vazio. Para o bloco H, há dois caminhos: um banco novo por rodada de suíte, ou filtros por IDs únicos nesses testes. Fica para decisão.

## Verificações complementares

- Depois das correções: `test_a9.py` + `test_i2.py` em SQLite (31 aprovados), `test_ready.py` em SQLite (2 aprovados), os três testes corrigidos em PostgreSQL vazio e compartilhado (aprovados).
- `ruff check .` e `ruff format --check .` sem erros.

## Não verificado

- A suíte inteira não rodou de novo em PostgreSQL depois das três correções; só os testes afetados.
- Agentes reais com LLM, Nginx/Compose e VPS ficam fora desta rodada.
- Backup e restauração das tabelas da 0010 (bloco H).

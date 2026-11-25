# Validação E — exportação canônica v2

Data da verificação: 21/11/2026. Worktree `team/backend`, HEAD `128f8af` (merge de `origin/main`) com alterações locais não commitadas de 31/10 a 02/11 e de 21/11.

## Origem deste registro

O exportador v2 ([formato e compatibilidade](exportacao-canonica.md)) e seus testes foram escritos em 02/11/2026, mas o relatório E citado pelos índices não chegou a ser gravado. Este arquivo não reconstrói resultados daquela data: registra apenas a execução feita em 21/11/2026 sobre o código atual.

## Comando e resultado

```powershell
uv run --locked python -m pytest -p no:cacheprovider tests/backend/test_e_export.py -rA
```

Resultado: 13 casos aprovados em 69,6 s, SQLite local. As linhas `storage_unavailable` no log vêm dos casos que injetam falha de armazenamento; são esperadas.

| Caso | O que confirma |
| --- | --- |
| `test_export_postcommit_retry_and_late_failure_without_sse` (2 tools de escrita) | Falha pós-commit, nova tentativa e falha tardia aparecem no arquivo sem depender do SSE |
| `test_export_rollback_and_unknown_completion_preserve_nulls` | Rollback e conclusão desconhecida ficam `null`, não zero nem sucesso |
| `test_legacy_stages_never_invent_physical_identity` (2 variantes) | Registros legados não ganham identidade de tentativa física inventada |
| `test_declaration_effect_and_evaluation_remain_separate` | Declarado pelo agente, observado pelo servidor e avaliado ficam em campos separados |
| `test_scope_kinds_empty_export_and_deterministic_output` | Filtros de escopo, exportação vazia e saída determinística |
| `test_snapshot_is_stable_during_concurrent_write` | Snapshot estável com escrita concorrente |
| `test_failed_publication_never_leaves_partial_or_overwrites` (sql, serialização, corrida) | Falha de publicação não deixa arquivo parcial nem sobrescreve o anterior |
| `test_cli_selects_benchmark_and_reports_safe_failure` | CLI seleciona execuções de benchmark e falha com mensagem segura |
| `test_structural_corruption_does_not_publish_unvalidated_receipt` | Corrupção estrutural não publica recibo sem validação |

## Limites

- Só SQLite. PostgreSQL 17 (bloco H) não foi executado: Docker não está disponível nesta máquina.
- Nenhum consumidor real (`evaluation/runner.py`, página de resultados) leu o JSONL v2 nesta verificação; a revisão da Metodologia continua pendente.
- Indicadores (bloco O) não foram calculados a partir do arquivo.

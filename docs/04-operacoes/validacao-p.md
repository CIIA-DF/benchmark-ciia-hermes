# Validação P — pendências da auditoria de 30/10/2026

Data: 22/11/2026. Worktree `team/backend`. Cada item foi reproduzido de novo antes da correção, porque o código mudou depois da auditoria. Itens já resolvidos em entregas anteriores ficam registrados como tais.

## Situação por item

| Item da auditoria | Situação | Commit / evidência |
| --- | --- | --- |
| 1. Falha de transporte vira chamada não observada (`result_integrity.py:48`) | **Decisão pendente** (abaixo). Não corrigido: a regra atual é decisão aceita do A2 | `test_a2.py::test_never_executed_is_rejected` e `test_failure_without_experiment_preserves_unobserved_transport_path` |
| 2. `X-Tool-Call-Id` opcional, mas exigido na prática (`tools.py`) | Corrigido: o ID efetivo volta no cabeçalho `X-Tool-Call-Id` da resposta, gerado ou enviado | `99ca645`; `test_p2_tool_call_id.py`: 3 de 4 falhavam antes, 4 passam |
| 3. U+0000 aceito em `Text`/`answer` (`contracts/models.py:19`) | Corrigido: o mesmo pattern do F2 em `Text`, `AgentEvent.text` e `AgentResult.answer`; mudança de contrato para revisão | `78337fc`; `test_p3_nul_text.py`: 6 de 7 falhavam antes, 7 passam |
| 4. Compose não repassa executores e limites (`infra/compose.yml`) | Corrigido: `ENABLED_EXECUTORS`, `RUN_*` e `CHAT_CONTEXT_MAX_CHARS` com os padrões do código; revisão da Infra | `276c061`; `docker compose config` |
| 5. CI sem job do portal | **Proposta**, não implementada: o `validate_repository` exige exatamente os jobs `quality` e `integration` (checks obrigatórios), e o SHA do `actions/setup-node` não foi conferido | — |
| 6. Isolamento no PostgreSQL reaproveitado (suíte de 21/11) | Corrigido nos testes, sem mudança no backend | `f4bdce9` e `5d465d7`; suíte completa no PostgreSQL compartilhado: 544 aprovados, 0 falhas |
| 7. `update`/lote do `scripts.provision` | Já resolvido no R1/P de 21/11 ([validação J](validacao-j.md)) | `test_i2.py`, `test_t0_r1.py` |
| 8. Timeouts do proxy no Compose | Já resolvido no I3/R2 | `test_i3.py` |
| 9. Desempenho: `text_delta` quadrático, claim que trava a fila, duas escritas por SSE a cada 200 ms, auditoria antes de autenticar | Não tratado nesta entrega: exige medição antes e depois | — |
| Blocos H e O | Não tratados nesta entrega | — |

## Item 1: decisão pendente

**O que acontece.** Se as 3 tentativas de uma tool falham no transporte (`ConnectError`), a requisição nunca chega ao servidor. O cliente comum registra a chamada como `error` em `tool_calls`. No `/result`, o servidor exige que as chamadas declaradas sejam exatamente as observadas, recusa com 422, e o run termina `failed` sem `ExperimentRun`, mesmo que o agente tenha se recuperado e respondido.

**Por que não mudei.** O A2 decidiu essa regra de propósito: chamada nunca observada é recusada mesmo declarada como `error`, e perda de transporte termina como falha sem registro. Afrouxar a regra deixa um agente declarar falhas sem evidência no servidor, o que altera denominadores da Metodologia.

**Opções.**

1. **Manter (A2).** O run é contado como falha de infraestrutura. Simples, mas o benchmark perde a execução inteira por uma falha de rede.
2. **Aceitar chamada só declarada**, com `status="error"` e sem artefato. Sucesso ou artefato sem observação continuam 422. A exportação já separa `declared` de `observed`, mas cabe à Metodologia como contar.
3. **Recomendada:** o cliente comum tira de `tool_calls` as chamadas que nunca receberam resposta e as registra em `ExperimentRun.parameters["unobserved_tool_calls"]`. Mantém o invariante do A2 (`tool_calls` igual ao histórico do servidor) e preserva a informação. Exige mudar `AsyncToolClient`/`normalized` e a concordância da Metodologia.

## Comandos e resultados

| Verificação | Resultado |
| --- | --- |
| `pytest tests/backend/test_p2_tool_call_id.py` antes / depois | 3 falhas, 1 aprovado / 4 aprovados |
| `pytest tests/backend/test_p3_nul_text.py` antes / depois | 6 falhas, 1 aprovado / 7 aprovados |
| Regressões das tools depois de P2/P3 (`test_f0`, `test_a0`, `test_a2`, `test_a13`, `test_tool_calls`, `test_tools`, `tests/integration/test_i1.py`) | 96 aprovados |
| Os 12 casos de isolamento no PostgreSQL 17 compartilhado (`ciia-h-postgres17`) antes / depois | 12 falhas / 12 aprovados; arquivos inteiros: 53 aprovados |
| Mesmos 6 arquivos em SQLite | 53 aprovados em três rodadas; numa rodada anterior, 1 falha intermitente não identificada (saída sem `-rf`), com a máquina carregada |
| `ruff check`, `ruff format --check`, `scripts.validate_repository`, `scripts.validate_api_docs`, `scripts.export_openapi --check` | Sem erros |

## Suíte completa

Seis grupos sequenciais, como em 21/11, em worktrees temporárias:

| Grupo | SQLite, `f4bdce9` | PostgreSQL 17 compartilhado, `f4bdce9` | PostgreSQL 17 compartilhado, `5d465d7` |
| --- | --- | --- | --- |
| `test_a*` | 122 aprovados | 122 aprovados | 122 aprovados |
| `test_f*` | 53 aprovados | 52 aprovados, 1 falha | 53 aprovados |
| `test_t*` | 150 aprovados | 149 aprovados, 1 falha | 150 aprovados |
| restante de `tests/backend` | 155 aprovados | 153 aprovados, 2 falhas | 155 aprovados |
| `tests/integration` | 57 aprovados | 57 aprovados | 57 aprovados |
| `tests/documents` | 7 aprovados | 7 aprovados | 7 aprovados |
| **Total** | **544 aprovados, 0 falhas** | **540 aprovados, 4 falhas** | **544 aprovados, 0 falhas** |

As 4 falhas no PostgreSQL sobre `f4bdce9` eram da mesma família do P6 e só aparecem com dados de rodadas anteriores: processo `OTHER` fixo (F4 e T4), perfil `rollback-profile` fixo e `local-operator` do bootstrap (I2). Foram corrigidas em `5d465d7`. Os testes alterados nesse commit passaram em SQLite (5 casos) e duas vezes seguidas no PostgreSQL. A suíte completa em SQLite não foi repetida sobre `5d465d7`, que só muda esses 3 arquivos de teste.

Em 21/11, o PostgreSQL deu 498 aprovados e 16 falhas. Os 544 de agora incluem os testes novos de K (catálogo), P2 e P3.

## Instabilidade observada

`test_f0.py::test_parallel_requests_keep_physical_identity_and_one_effect` (duas escritas paralelas em SQLite) falhou uma vez na suíte completa sobre `3b70706`, enquanto outras verificações rodavam na mesma máquina, e passou 8 de 8 vezes isolado. Fica registrado, sem ajuste no teste.

## Não verificado

- Itens 1, 5, 9, H e O (motivos acima).
- P2 com clientes reais (Hermes/LangGraph) e P3 com corpus real dos Documentos.
- CI remoto: nada foi enviado ao GitHub.

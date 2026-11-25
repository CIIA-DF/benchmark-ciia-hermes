# Validação P — pendências da auditoria de 30/10/2026

Data: 22/11/2026. Worktree `team/backend`. Cada item foi reproduzido de novo antes da correção, porque o código mudou depois da auditoria. Itens já resolvidos em entregas anteriores ficam registrados como tais.

## Situação por item

| Item da auditoria | Situação | Commit / evidência |
| --- | --- | --- |
| 1. Falha de transporte vira chamada não observada (`result_integrity.py:48`) | **Opção 3 escolhida pelo responsável em 25/11** (abaixo) e implementada no [P10](validacao-p2.md#p10--item-1-perda-de-transporte); aceite da Metodologia pendente. A regra do A2 continua valendo para `tool_calls` | `test_a2.py::test_never_executed_is_rejected` e `test_failure_without_experiment_preserves_unobserved_transport_path` |
| 2. `X-Tool-Call-Id` opcional, mas exigido na prática (`tools.py`) | Corrigido: o ID efetivo volta no cabeçalho `X-Tool-Call-Id` da resposta, gerado ou enviado | `d082d87`; `test_p2_tool_call_id.py`: 3 de 4 falhavam antes, 4 passam |
| 3. U+0000 aceito em `Text`/`answer` (`contracts/models.py:19`) | Corrigido: o mesmo pattern do F2 em `Text`, `AgentEvent.text` e `AgentResult.answer`; mudança de contrato para revisão | `c98eec0`; `test_p3_nul_text.py`: 6 de 7 falhavam antes, 7 passam |
| 4. Compose não repassa executores e limites (`infra/compose.yml`) | Corrigido: `ENABLED_EXECUTORS`, `RUN_*` e `CHAT_CONTEXT_MAX_CHARS` com os padrões do código; revisão da Infra | `71f2fb6`; `docker compose config` |
| 5. CI sem job do portal | Resolvido pela `main` (Infra), incorporado no merge de 25/11: job `portal` com `npm ci`, `tsc --noEmit` e build; `validate_repository` passa a exigir `quality`, `integration` e `portal`. O SHA do `actions/setup-node` não foi conferido aqui | `77cceb5` (`main`), merge `04a4a7b` |
| 6. Isolamento no PostgreSQL reaproveitado (suíte de 21/11) | Corrigido nos testes, sem mudança no backend | `4082ea2` e `584f731`; suíte completa no PostgreSQL compartilhado: 544 aprovados, 0 falhas |
| 7. `update`/lote do `scripts.provision` | Já resolvido no R1/P de 21/11 ([validação J](validacao-j.md)) | `test_i2.py`, `test_t0_r1.py` |
| 8. Timeouts do proxy no Compose | Já resolvido no I3/R2 | `test_i3.py` |
| 9. Desempenho: `text_delta` quadrático, claim que trava a fila, duas escritas por SSE a cada 200 ms, auditoria antes de autenticar | Não tratado nesta entrega: exige medição antes e depois | — |
| Blocos H e O | Não tratados nesta entrega | — |

## Item 1: opções avaliadas em 22/11

Registro original da decisão, mantido como histórico. Em 25/11 o responsável escolheu a opção 3, implementada no [P10](validacao-p2.md#p10--item-1-perda-de-transporte).

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

## Efeitos do P3 corrigidos em 25/11/2026

A revisão de código de 25/11 apontou duas consequências do P3. As duas foram reproduzidas por teste antes da correção.

**Dados antigos com U+0000.** Linhas gravadas antes do P3 (o SQLite aceita o caractere em texto; o tipo `json` do PostgreSQL aceita o escape `\u0000`) passariam a falhar na leitura: `POST /runs/claim` responderia 500 depois de gravar a reserva, e `GET /runs/{id}` e a exportação também falhariam. A migração `0011` procura U+0000 em todas as colunas de texto e JSON. Se encontrar, interrompe a atualização na mesma transação, informando só tabela, coluna e número de linhas, sem conteúdo. O banco continua na `0010` e nada é alterado; `GET /ready` fica em 503 até a atualização.

Tratamento: faça backup. Uma base de demonstração com dados sintéticos pode ser recriada pelo fluxo de [chat](chat.md). Numa base relevante, trate as linhas indicadas, por exemplo trocando U+0000 por U+FFFD, e registre a mudança. Alterar `payload` de artefato invalida o hash do recibo, e esse artefato passa a responder `500 invalid_response`.

**Resposta do modelo com U+0000 na `RunBridge`.** A resposta era validada fora do `try`; o worker gravava `failed/adapter_error` mesmo com a revisão final já salva em `/experiments`. Agora a resposta é tratada dentro do `try`: cada U+0000 vira U+FFFD, e um evento `status` registra quantos foram trocados. O `ExperimentRun` não tem campo de resposta, então o registro experimental não muda. Adaptadores nativos (`AgentAdapter.stream`) continuam responsáveis pelos próprios eventos.

| Verificação | Resultado |
| --- | --- |
| `pytest tests/backend/test_compat.py -k nul` sem a correção da ponte / com a correção | 2 falhas / 2 aprovados (chat e benchmark) |
| `pytest tests/backend/test_p3_legacy_nul.py` | 3 aprovados: JSON e texto com U+0000 interrompem a `0011` sem expor conteúdo nem alterar a linha; barra invertida literal (`\u0000`) não é acusada |
| `test_p3_legacy_nul`, `test_compat`, `test_p3_nul_text`, `test_migrations` e `test_ready` (head `0011`) | 29 aprovados em SQLite |

A `0011` só foi aplicada a bancos PostgreSQL vazios (os testes migram até o head); a recusa com U+0000 em JSON no PostgreSQL fica para o bloco H.

### Suíte de 25/11/2026, depois do merge de `origin/main` (`04a4a7b`)

| Execução | Resultado |
| --- | --- |
| `scripts.dev check` em SQLite: lint, formato, validação do repositório e suíte completa | 546 aprovados, 3 falhas, 2.859,85 s |
| Suíte completa no PostgreSQL 17 compartilhado (`pg-p6-test`), rodada por outra sessão ao mesmo tempo, na mesma worktree | 3 falhas; total de aprovados não registrado. A repetição foi encerrada por falta de memória |
| Os 6 testes que falharam nas duas rodadas, isolados, em SQLite, duas vezes | 28 aprovados nas duas |
| Os mesmos 6 testes e `test_p3_legacy_nul.py` num PostgreSQL 17 novo e descartável | 31 aprovados, 43,78 s |

Falhas e causa provável:

- `test_a13.py::test_concurrent_last_slot_has_one_write_and_distinct_physical_receipts` e `test_a4.py::test_queue_races_use_one_operator_lock_for_both_producers[benchmark-and-chat]`, em SQLite: 503 `storage_unavailable` no lugar de 429. É a trava do SQLite esgotando o tempo de espera com duas suítes completas e outro projeto rodando na máquina e a memória livre abaixo de 1 GB.
- `test_f1.py::test_process_outcome_has_one_physical_attempt_and_durable_logical_reservation[inventory-500-invalid_response]`, em SQLite: 409 no lugar de 500. **Causa não identificada**; não se repetiu isolado. Fica registrado junto da instabilidade do `test_f0` abaixo.
- `test_ready.py::test_ready_reports_head_revision`, no PostgreSQL: a rodada começou antes da `0011` e da mudança do teste para `0011`; o módulo carregado esperava `0010` e o head lido do disco já era `0011`.
- `test_a9.py::test_separate_processes_cannot_overbook_last_slot` e `test_i3.py::test_actual_proxy_route_with_synthetic_transport[wire_sse]`, no PostgreSQL: corrida entre subprocessos e probe em Node, sensíveis a carga; passaram isolados nos dois bancos.

Não houve uma suíte completa sem falhas depois do merge. A próxima suíte completa, em SQLite e PostgreSQL isolado (P8), roda sozinha na máquina ao fechar a Fase 2.

## Suíte completa

Seis grupos sequenciais, como em 21/11, em worktrees temporárias:

| Grupo | SQLite, `4082ea2` | PostgreSQL 17 compartilhado, `4082ea2` | PostgreSQL 17 compartilhado, `584f731` |
| --- | --- | --- | --- |
| `test_a*` | 122 aprovados | 122 aprovados | 122 aprovados |
| `test_f*` | 53 aprovados | 52 aprovados, 1 falha | 53 aprovados |
| `test_t*` | 150 aprovados | 149 aprovados, 1 falha | 150 aprovados |
| restante de `tests/backend` | 155 aprovados | 153 aprovados, 2 falhas | 155 aprovados |
| `tests/integration` | 57 aprovados | 57 aprovados | 57 aprovados |
| `tests/documents` | 7 aprovados | 7 aprovados | 7 aprovados |
| **Total** | **544 aprovados, 0 falhas** | **540 aprovados, 4 falhas** | **544 aprovados, 0 falhas** |

As 4 falhas no PostgreSQL sobre `4082ea2` eram da mesma família do P6 e só aparecem com dados de rodadas anteriores: processo `OTHER` fixo (F4 e T4), perfil `rollback-profile` fixo e `local-operator` do bootstrap (I2). Foram corrigidas em `584f731`. Os testes alterados nesse commit passaram em SQLite (5 casos) e duas vezes seguidas no PostgreSQL. A suíte completa em SQLite não foi repetida sobre `584f731`, que só muda esses 3 arquivos de teste.

Em 21/11, o PostgreSQL deu 498 aprovados e 16 falhas. Os 544 de agora incluem os testes novos de K (catálogo), P2 e P3.

## Instabilidade observada

`test_f0.py::test_parallel_requests_keep_physical_identity_and_one_effect` (duas escritas paralelas em SQLite) falhou uma vez na suíte completa sobre `c9aeda8`, enquanto outras verificações rodavam na mesma máquina, e passou 8 de 8 vezes isolado. Fica registrado, sem ajuste no teste.

## Não verificado

- Itens 1, 9, H e O (motivos acima). O item 1 segue a opção 3 por decisão do responsável em 25/11; implementação prevista no próximo sub-bloco.
- P2 com clientes reais (Hermes/LangGraph) e P3 com corpus real dos Documentos.
- CI remoto: nada foi enviado ao GitHub.

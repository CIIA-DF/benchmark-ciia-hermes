# Validação J — port do registro experimental do LangGraph

Data: 21/11/2026. Worktree `team/backend`, HEAD `128f8af`, com alterações locais sem commit. Origem do trabalho portado: `task/langgraph-grafo`, commit `856ff06` (João Enomoto, 18/11/2026). A branch do LangGraph não foi alterada. [ADR 011](../05-decisoes/011-registro-experimental-revisoes.md).

## O que mudou

- **Rotas `/experiments`:** `POST /experiments`, `GET /experiments/{run_id}`, `PUT /experiments/{run_id}` e `GET /experiments/{run_id}/revisions`, com as regras de revisão do original. A v0.2 acrescenta autenticação, reserva, escopo e conferência com o histórico ([services/backend/experiments.py](../../services/backend/experiments.py)). Migração `0010`.
- **Resultado do run:** um resultado com `experiment` precisa trazer a última revisão gravada.
- **`agents/interface.py`:** `ExperimentRunClient` com a mesma interface do original e `token`/`run_token` opcionais; `timeout_seconds` no `ToolClient`.
- **`agents/compat.py`:** `ExperimentSink` (`save`/`get`/`update`) e fábrica de três argumentos na `RunBridge`. O registro passa a usar as chamadas e os artefatos do cliente comum.
- **`GET /ready`:** schema na revisão Alembic esperada.
- **`scripts/benchmark_batch.py`:** runs em lote com idempotência por rótulo, ordem intercalada e janela.
- **Exportação JSONL v2:** ganha `declared.experiment_revisions`.

## Comandos e resultados

| Verificação | Resultado |
| --- | --- |
| Linha de base antes das mudanças de 21/11, em cópia isolada, 6 grupos | 465 testes, 0 falhas |
| `pytest tests/backend/test_experiment_runs.py` | 15 aprovados: os 4 testes do original adaptados, mais credenciais, reserva, escopo, histórico, reserva expirada, resultado × última revisão, corrida, migração 0010, exportação, registro sem `revision` e worker sem concessão |
| `pytest tests/backend/test_compat.py` | 11 aprovados: a ponte de antes, mais o sink com 1 e 2 revisões, o sink no chat e `normalized` |
| `pytest tests/backend/test_benchmark_batch.py` | 6 aprovados, incluindo 429 `resource_limit` com espera do worker |
| `pytest tests/backend/test_ready.py tests/backend/test_openapi.py` | 4 aprovados |
| Conferência cruzada em árvore temporária: `agents/langgraph/` e os testes do `856ff06` sobre a v0.2 portada, venv temporário com langgraph 1.2.18 e langchain-core 1.7.1 | 10 aprovados: os 9 testes originais do João e o `LangGraphAdapter` real (modelo falso) pela `RunBridge`, pelo worker e por `/experiments` |
| `ruff check .`, `ruff format --check .`, `scripts.validate_repository`, `scripts.validate_api_docs` (26 operações), `scripts.export_openapi --check` | Sem erros |

Na conferência cruzada, o grafo do LangGraph executou as duas tools em paralelo. A ordem de `tool_calls` segue a conclusão das chamadas, e o servidor aceitou o registro nas duas ordens.

## Revisão de código (21/11)

`/code-review medium` sobre a worktree `team/backend`. Corrigidos no working tree, com teste:

- Registro sem `parameters.revision`: o servidor grava a revisão 1, mas o `ExperimentRunClient` acusava divergência na releitura e `POST /runs/{id}/result` recusava o relatório original com 422. Agora `canonical()` e o cliente tratam a ausência como revisão 1. O problema da releitura já existia no `856ff06`.
- Worker do executor certo sem concessão no processo recebia 403 em `GET /experiments/{run_id}`, o que confirmava o `run_id`; agora recebe 404.
- Timeout de `/experiments` dentro do `ExperimentSink` virava `model_timeout`; agora é `adapter_error`.
- `ENABLED_EXECUTORS` com espaços (`"hermes, langgraph"`) desabilitava executores; agora os nomes são aparados.
- O comentário de `OPENROUTER_API_KEY` no `.env.example` passa a citar a origem (`team/hermes`, `agents/hermes/adapter.py`).

Achados de entregas anteriores a 21/11, conferidos contra a `main` e os documentos da `team/backend`:

| Bloco | Achado | Decisão | Evidência |
| --- | --- | --- | --- |
| R1 | `scripts.provision` com vários perfis aplicava parte antes de recusar | Corrigido: o lote é conferido antes da primeira escrita (create: todos ausentes; update/rotate: todos existentes), `principal_id` ou token repetido é recusado antes do banco, e a mensagem informa "Perfis aplicados: k de n" sem identificar perfis ([chat](chat.md#perfis-e-permissões)) | `tests/backend/test_i2.py` + `test_t0_r1.py`: 30 aprovados |
| R1 | Bootstrap não avisava quando o token do ambiente difere do perfil gravado | Corrigido só o aviso: `bootstrap_token_mismatch principal_id=…`, sem token nem hash. O perfil continua preservado, como o I2 exige | idem |
| R2 | Proxy do portal tratava variável de timeout vazia como 0 (503) | Corrigido: vazio ou só espaços usa o padrão (20 s / 30 s), como `${VAR:-20}` no Compose; `0`, negativo e não finito continuam recusados | `tests/integration/test_i3.py`: 20 aprovados, com o cenário novo `blank_timeout` |
| R3 | Exportação depende de `os.link` (falha em FAT/exFAT) | Não corrigido: [exportação canônica](exportacao-canonica.md) define que o volume deve permitir hard links e que não há fallback para sobrescrita | — |
| R3 | Sonda `bootstrap_restores_local_write_and_grant` do `audit_backend` agora dá `false` | Não é defeito: a sonda reproduz o achado 05 de 28/10, corrigido no I2. `scripts/README.md` explica a leitura; o relatório de 28/10 fica como registro datado | — |

O guia de `portal/node_modules/next/dist/docs/` pedido por `portal/AGENTS.md` não existe na versão instalada do Next. A mudança do R2 não usa API do Next, só a leitura da variável de ambiente.

## Segunda revisão de código (21/11)

Nova rodada do `/code-review` na worktree `team/backend`, depois das correções acima. Os 5 achados foram conferidos no código e corrigidos no working tree, com teste:

| Bloco | Achado | Correção | Evidência |
| --- | --- | --- | --- |
| C | As docstrings de classe de `contracts/models.py` viravam `description` no catálogo de tools enviado ao modelo. `consultar_processo` e `consultar_requisitos` levavam texto sobre campos ausentes | `tool_catalog()` remove do topo e de `$defs` só as docstrings de classe. Elas continuam no OpenAPI (ADR 010) | `test_f2.py` + `test_chat_delivery.py`: 17 aprovados |
| P | `scripts.provision` ainda podia aplicar parte do lote: worker sem executor ou token de outro perfil só falhavam no laço | `check_profile()` (extraída de `provision()`) roda antes do banco, e a conferência prévia busca colisões de credencial no banco | `test_i2.py` + `test_t0_r1.py`: 34 aprovados em SQLite. No PostgreSQL compartilhado, só as 2 falhas de isolamento já registradas |
| P | `--operation update` sem `can_write` gravava `False` e revogava a escrita | `can_write` obrigatório em create e update, como role e grants ([chat](chat.md#perfis-e-permissões)) | idem |
| B | Na ponte, o relatório final do adaptador era descartado em favor da última revisão do sink | Se o relatório final diferir da última revisão gravada (`revision` ausente = 1), a ponte encerra com `adapter_error`; não grava revisões pelo adaptador ([integração](integracao-agentes.md)) | `test_compat.py` + `test_experiment_runs.py`: 27 aprovados |
| L | A chave `rotulo:tarefa:executor:repeticao` podia colidir, porque rótulo e `task_id` aceitavam `:` | Rótulo, `task_id` e executor sem `:` | `test_benchmark_batch.py`: 9 aprovados |

**Catálogo em relação ao `HEAD`:** sem as docstrings de classe, o catálogo ainda difere do `HEAD` (`128f8af`). As descrições das seis tools foram reescritas e os campos de entrada ganharam `description`, ambas alterações locais deliberadas anteriores a 21/11, recomendadas no [levantamento de documentação](levantamento-documentacao-backend.md). Isso muda o prompt enviado ao modelo. A versão do catálogo precisa ser congelada e revisada com Hermes, LangGraph e Metodologia antes da coleta, para que os runs sejam comparáveis.

Também ficaram únicos os IDs dos testes de lote de 21/11 (`batch-*`), que falhavam no PostgreSQL compartilhado.

## Terceira revisão de código (21–22/11)

`/code-review` e `/engineering:code-review` sobre o diff local. O plano foi conferido com o protocolo da Metodologia (`evaluation/protocol.md` em `team/evaluation`, só leitura), que acrescentou ordem contrabalançada e manifesto completo.

| Bloco | Achado | Correção | Evidência |
| --- | --- | --- | --- |
| S | A regra "sem `revision` = revisão 1" estava em 3 lugares, e `TERMINAL` em outros 3 | `experiment_record()` e `FIRST_REVISION` em `contracts/models.py`; `TerminalStatus` e `TERMINAL_STATUSES` em `contracts/execution.py`. Servidor, `ExperimentRunClient`, ponte e lote importam as mesmas regras; OpenAPI sem mudança | `test_experiment_contract.py` + `test_experiment_runs.py` + `test_compat.py`: 30 aprovados |
| B | `benchmark_batch`: prazo único de 3600 s para o lote inteiro | Prazo sem progresso (`--stall-seconds`, padrão 1200 s), renovado a cada run aceito ou terminado | `test_benchmark_batch.py`: 14 aprovados |
| B | `benchmark_batch` sem novas tentativas para 503 ou erro de transporte | Espera crescente (1, 2, 4… até 30 s) para `httpx.TransportError` e 5xx `retryable`; 401/403/422 continuam definitivos. Repetir o `POST` é seguro pela chave idempotente | idem |
| B | Protocolo: ordem "aleatória/contrabalanceada" | A ordem dos executores gira por tarefa e repetição, determinística; `position` no manifesto | idem; `--dry-run` conferido com tarefas sintéticas |
| B | Protocolo: "relatar todas as execuções previstas" | Lote interrompido emite `not_submitted` para os itens restantes | idem |
| E | Comentário da exportação afirmava que a última revisão sempre coincide com `result.experiment` | Comentário e [exportação canônica](exportacao-canonica.md) corrigidos: um run que falhou pode ter revisões e `declared.experiment` nulo | `test_experiment_runs.py` + `test_e_export.py`: 29 aprovados |

Também foi corrigido o `--help` do `benchmark_batch`, que quebrava no console Windows (cp1252) por causa de uma seta na docstring.

Ficam para o bloco H: limite de revisões por run, cache da head e duas heads no `/ready`, tipos de `check_profile` e `/ready` só na rede interna.

## Não verificado

- **Suíte completa:** rodou depois, em seis grupos. SQLite: 514 aprovados, 0 falhas. PostgreSQL 17 compartilhado: 498 aprovados e 16 falhas, das quais 2 eram defeitos de teste (corrigidos, mais um terceiro achado antes da suíte em `test_ready.py`) e 14 são de isolamento em banco reaproveitado (passam num banco vazio). Ver [suíte de 21/11](validacao-suite-2026-11-21.md). A suíte inteira em PostgreSQL não rodou de novo depois das correções.
- **Agentes reais:** Hermes e LangGraph com LLM real (OpenRouter) não foram testados; só o modelo falso dos testes do João.
- **Revisões:** não houve revisão do LangGraph nem da Metodologia.

# Hermes — adaptador experimental

O pacote/runtime Hermes oficial não foi instalado ou confirmado por este projeto. A coordenação ainda deve confirmar URL, versão/commit, licença e identidade do executor; o adaptador usa diretamente o protocolo HTTP OpenAI-compatible solicitado, sem presumir capacidades de um pacote Hermes (ADR pendente).

Ponto de entrada comum: [AgentAdapter, ModelConfig e ToolClient](../interface.py). [adapter.py](adapter.py) implementa o loop ReAct sobre o catálogo completo de 6 ferramentas definidas em [tools.py](tools.py) (compatível e delegável a `contracts.catalog.openai_tools()` e `catalog_version()`). Envelopes de tool call malformados são solicitados novamente; argumentos JSON inválidos geram um erro correlacionado pelo ID da chamada, sem invocar a ferramenta. A injeção estrita de `ToolContext` (`inject_tool_context`) impede que o LLM substitua chaves autenticadas (`run_id`, `process_id`, `corpus_version`, `requirements_version`).

Erros das tools seguem a separação da arquitetura do Backend:
- **Corrigíveis (`validation_error`, `not_found`, `idempotency_conflict`, `not_implemented`):** repassados ao modelo no envelope `{"error": {"code": ..., "message": ...}}` para tentativa de correção ou declaração de limitação.
- **Definitivos (`ToolCallError`, HTTP 401/403, `version_mismatch`, `budget_exceeded`, `run_expired`):** encerram imediatamente a execução sem retornar à LLM.
- **Não observados pelo servidor (P10 — `ConnectError`, `ConnectTimeout`, `PoolTimeout`):** contabilizados em `ExperimentRun.parameters["unobserved_tool_calls"]` e mantidos fora de `ExperimentRun.tool_calls`.

A LLM aceita `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`; `OPENROUTER_API_KEY` é fallback para a chave. Headers OpenRouter opcionais: `OPENROUTER_HTTP_REFERER` e `OPENROUTER_TITLE` (enviados como `HTTP-Referer` e `X-OpenRouter-Title`). `BACKEND_URL` direciona as ferramentas; o padrão é `http://127.0.0.1:8000`. O smoke `uv run --locked python -m agents.smoke --adapter hermes` continua verificando somente HTTP; não integra a LLM.

## Integração com Worker (`RunBridge`) e Execução via CLI

Fábrica sem argumentos para o worker (`agents.worker`):
```sh
uv run --locked python -m agents.worker --executor hermes --adapter agents.hermes.adapter:adapter
```

Execução direta via CLI (`agents.hermes.run`):
```sh
uv run --locked python -m agents.hermes.run --task-id DEV-001 --split development --repetition 1 --save
uv run --locked python -m agents.hermes.run --all --split development --save
```

Parâmetros suportados:
- `--task-id`: identificador de uma tarefa em `evaluation/tasks.json` (padrão: `DEV-001`).
- `--task-ids`: lista de identificadores separados por vírgula (ex.: `DEV-001,DEV-002`).
- `--all`: executa todas as tarefas do `split` selecionado.
- `--split`: split de avaliação (`development` ou `final`, padrão: `development`).
- `--repetition`: número sequencial da repetição (padrão: `1`).
- `--save`: grava o `ExperimentRun` em `evaluation/results/{run_id}.json`.

## Quadro de tarefas (Hugo Coelho / HugoDev999)

| ID | Tarefa | Responsável | Status | Detalhes |
|---|---|---|---|---|
| **HM-01** | Implementação inicial do loop ReAct e testes unitários com mock | Hugo Coelho | Concluído | Entregue nos commits `356a189`, `7685192`, etc. |
| **HM-02** | Isolamento estrito de `ToolContext` e blindagem contra adulteração de `run_id`/`process_id` | Hugo Coelho / Agente Hermes | Concluído | Garantida sobrescrita segura dos argumentos pelo `inject_tool_context`. |
| **HM-03** | Suporte ao catálogo completo de 6 tools, `catalog_version()` e integração com `contracts.catalog` | Hugo Coelho / Backend / Agente Hermes | Concluído | `agents/hermes/tools.py` com `_clean_schema`, `openai_tools()` e `catalog_version()`. |
| **HM-04** | Resolução de `task_id`, precificação ADR 003 (`cost_usd`) e CLI em lote (`--all` / `--save`) | Hugo Coelho / Agente Hermes | Concluído | `_resolve_task_id`, `_calculate_cost_usd` (Camadas 1 e 2) e suporte a lote em `run.py`. |
| **HM-05** | Adequação ao Worker/Backend (`RunBridge`, `tool_client` injetado, `ToolCallError` e P10 `unobserved_tool_calls`) | Agente Hermes | Concluído | `adapter()`, `create_adapter()`, `run_with_result()`, `sink` e testes de integração e2e. |

Próxima etapa: registrar identidade em ADR oficial quando confirmada pela coordenação e executar a coleta final pareada (`Hermes × LangGraph`). [Guia da equipe](../../docs/03-equipes/hermes.md).

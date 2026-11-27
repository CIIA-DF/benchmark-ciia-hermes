# Hermes

Integrantes: 1 | Monitor: Gustavo Antônio. Branch: `team/hermes`.

- **Monitor:** Gustavo Antônio
- **Integrantes:**
  - Hugo Coelho Teixeira (3° semestre eng. de software)

## Objetivo e responsabilidades

Construir e integrar o agente autônomo baseado em Hermes às ferramentas REST compartilhadas do SEI e ao protocolo comum de benchmark.

A frente está dividida em duas etapas claras:
1. **Construção do Agente e Runtime Operacional:** Modelagem do loop ReAct/tool calling, schemas de chamadas, prompts de sistema com foco em citação estrita de evidências e tratamento de erros/timeouts.
2. **Harness de Benchmark e Instrumentação:** Coleta estruturada de logs (`ExperimentRun`), rastreabilidade de chamadas (`run_id`), medição de tokens/latência/custo e conexão com o worker (`RunBridge`) e com a frente de Metodologia para o pareamento experimental com o LangGraph.

Limites: Não instalar um homônimo sem auditar a fonte. Não duplicar ferramentas de negócio ou acessar o banco diretamente (usar sempre `ToolClient` ou o cliente injetado pelo worker). Não alterar schemas de contratos sem alinhamento com Backend.

As definições OpenAI/ChatML do catálogo completo das 6 ferramentas ficam em `agents/hermes/tools.py` (delegando automaticamente para `contracts.catalog.openai_tools()` e `catalog_version()` quando presentes) e derivam seus parâmetros dos modelos de entrada em `contracts/models.py`.

## Quadro de tarefas da equipe (Hugo Coelho / HugoDev999)

Abaixo está o registro transparente das tarefas atribuídas e executadas na frente Hermes:

| ID | Tarefa | Responsável | Status | Detalhes / Evidência |
|---|---|---|---|---|
| **HM-01** | Implementação inicial do loop ReAct e testes unitários com mock | Hugo Coelho | Concluído | Entregue nos commits `356a189`, `7685192`, etc. |
| **HM-02** | Isolamento estrito de `ToolContext` e blindagem contra adulteração de `run_id`/`process_id` | Hugo Coelho / Agente Hermes | Concluído | Revisado e completado garantindo sobrescrita segura via `inject_tool_context`. |
| **HM-03** | Suporte ao catálogo completo de 6 tools, `catalog_version()` e integração com `contracts.catalog` | Hugo Coelho / Backend / Agente Hermes | Concluído | Catálogo de 6 ferramentas em `agents/hermes/tools.py` com `_clean_schema`, `openai_tools()` e hash SHA-256 canônico em `ExperimentRun.parameters["catalog_version"]`. |
| **HM-04** | Resolução automática de `task_id`, tabela de custos ADR 003 (`cost_usd`) e CLI em lote (`--all` / `--save`) | Hugo Coelho / Agente Hermes | Concluído | `_resolve_task_id`, `_calculate_cost_usd` para modelos das Camadas 1 e 2 e CLI com execução unitária ou em lote. |
| **HM-05** | Adequação ao Worker/Backend (`RunBridge`, injeção de `tool_client`/`sink`/`execution`, `ToolCallError` e P10 `unobserved_tool_calls`) | Agente Hermes | Concluído | Fábrica `agents.hermes.adapter:adapter`, `run_with_result()`, encerramento imediato em erros definitivos, contagem `unobserved_tool_calls` e teste e2e contra FastAPI/SQLite. |

> **Nota Arquitetural:** O runtime atual é um adaptador ReAct experimental OpenAI-compatible aderente aos contratos comuns (`contracts/models.py`), sem invenção de APIs não confirmadas. A definição de pacote oficial/versão do Hermes permanece como ADR pendente com a coordenação.

## Entradas, saídas e dependências

Recebe tarefa, ToolContext, endpoint/modelo aprovados e API; entregará resultado e ExperimentRun rastreável.

Coordenação confirma Hermes; Backend fornece ferramentas; Infra fornece configuração; Metodologia define limites/métricas e revisão cruzada com LangGraph.

Pastas: agents/hermes/; agents/interface.py é compartilhado e exige revisão da outra equipe.

## Estudar e executar

Documentação oficial do Hermes confirmado, tool calling, HTTP, timeouts, estado, encerramento e instrumentação.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo para popular a base sintética. Em outro terminal, inicie a API com `uv run --locked python -m scripts.dev serve`. Com a API local ativa em `http://127.0.0.1:8000`, configure `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY` no terminal do agente e execute uma tarefa de avaliação:

```sh
uv run --locked python -m agents.hermes.run --task-id DEV-001 --split development --repetition 1 --save
```

O comando lê a tarefa de `evaluation/tasks.json`, chama `HermesAdapter` com o contexto dessa tarefa e imprime a resposta final, um resumo estruturado da execução e o `ExperimentRun` em JSON. Com `--save`, salva o resultado em `evaluation/results/{run_id}.json`. O adapter usa `http://127.0.0.1:8000` para as ferramentas (ou o cliente injetado via `RunBridge`). A chamada à LLM usa o endpoint e as credenciais configurados no ambiente; o smoke `uv run --locked python -m agents.smoke --adapter hermes` continua testando apenas a interface HTTP, sem executar o agente real.

## Primeiras tarefas

1. **Definição de Runtime e Dependências:** Fixar repositório/pacote oficial (Nous Research / Hermes Tool Calling), licença e travar no `pyproject.toml`.
2. **Loop de Tool Calling e Adapters:** Implementar `HermesAdapter(AgentAdapter)` conectando o loop autônomo ao `ToolClient` para consumir o catálogo de ferramentas.
3. **Engenharia de Prompt e Regras SEI:** Desenvolver o System Prompt orientando o agente a citar evidências físicas (processo, documento e página), respeitar limitações de bases parciais e não inventar fatos em buscas vazias.
4. **Instrumentação e Coleta para Benchmark:** Estruturar a geração de `ExperimentRun` (tokens, custo USD, latência, `catalog_version`, `unobserved_tool_calls`, histórico de chamadas e controle rígido por `run_id`).

## Critério de conclusão

Agente Hermes funcional resolvendo tarefas sintéticas e reais via chamadas ao backend, com exportação de `ExperimentRun` auditável e pronta para execução no harness pareado de benchmark. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

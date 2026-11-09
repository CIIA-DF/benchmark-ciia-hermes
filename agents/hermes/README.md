# Hermes — adaptador experimental

O pacote/runtime Hermes oficial não foi instalado ou confirmado por este projeto. A coordenação ainda deve confirmar URL, versão/commit, licença e identidade do executor; o adaptador usa diretamente o protocolo HTTP OpenAI-compatible solicitado, sem presumir capacidades de um pacote Hermes (ADR pendente).

Ponto de entrada comum: [AgentAdapter, ModelConfig e ToolClient](../interface.py). [adapter.py](adapter.py) implementa o loop ReAct sobre o catálogo completo de 6 ferramentas definidas em [tools.py](tools.py). Envelopes de tool call malformados são solicitados novamente; argumentos JSON inválidos geram um erro correlacionado pelo ID da chamada, sem invocar a ferramenta. A injeção estrita de `ToolContext` (`inject_tool_context`) impede que o LLM substitua chaves autenticadas (`run_id`, `process_id`, `corpus_version`, `requirements_version`). Erros do backend (`ToolError` em status HTTP não 2xx) são encapsulados e repassados ao modelo no formato `{"error": {"code": ..., "message": ...}}`.

A LLM aceita `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`; `OPENROUTER_API_KEY` é fallback para a chave. Headers OpenRouter opcionais: `OPENROUTER_HTTP_REFERER` e `OPENROUTER_TITLE` (enviados como `HTTP-Referer` e `X-OpenRouter-Title`). `BACKEND_URL` direciona as ferramentas; o padrão é `http://127.0.0.1:8000`. O smoke `uv run --locked python -m agents.smoke --adapter hermes` continua verificando somente HTTP; não integra a LLM.

## Execução via CLI

```sh
uv run --locked python -m agents.hermes.run --task-id DEV-001 --split development --repetition 1 --save
```

Parâmetros suportados:
- `--task-id`: identificador da tarefa em `evaluation/tasks.json` (padrão: `DEV-001`).
- `--split`: split de avaliação (`development` ou `final`, padrão: `development`).
- `--repetition`: número sequencial da repetição (padrão: `1`).
- `--save`: grava o `ExperimentRun` em `evaluation/results/{run_id}.json`.

## Quadro de tarefas (Hugo Coelho / HugoDev999)

| ID | Tarefa | Responsável | Status | Detalhes |
|---|---|---|---|---|
| **HM-01** | Implementação inicial do loop ReAct e testes unitários com mock | Hugo Coelho | Concluído | Entregue nos commits `356a189`, `7685192`, etc. |
| **HM-02** | Isolamento estrito de `ToolContext` e blindagem contra adulteração de `run_id`/`process_id` | Hugo Coelho / Agente Hermes | Concluído | Garantida sobrescrita segura dos argumentos pelo `inject_tool_context`. |
| **HM-03** | Suporte ao catálogo completo de 6 tools sem vazamento de contexto no schema | Hugo Coelho / Backend / Agente Hermes | Concluído | `agents/hermes/tools.py` expondo catálogo com `_clean_schema`. |
| **HM-04** | Parametrização de `task_id`, `split` e `repetition` para integração pareada e CLI `--save` | Agente Hermes | Concluído | Propagação completa no `ExperimentRun` e opções de CLI com salvamento em disco. |
| **HM-05** | Execução do benchmark piloto pareado e relatório de latência/tokens | Hugo Coelho / Metodologia | Em andamento | Pareamento experimental e benchmark piloto conjunto. |

Próxima etapa: registrar identidade em ADR, verificar documentação oficial e mapear seleção/chamada de ferramentas, estado, encerramento e logs ao contrato comum. Não inventar nomes de métodos ou capacidades. [Guia da equipe](../../docs/03-equipes/hermes.md).

# Hermes

Integrantes: 1 | Monitor: Gustavo Antônio. Branch: `team/hermes`.

- **Monitor:** Gustavo Antônio
- **Integrantes:**
  - Hugo Coelho Teixeira (3° semestre eng. de software)

## Objetivo e responsabilidades

Construir e integrar o agente autônomo baseado em Hermes às ferramentas REST compartilhadas do SEI e ao protocolo comum de benchmark.

A frente está dividida em duas etapas claras:
1. **Construção do Agente e Runtime Operacional:** Modelagem do loop ReAct/tool calling, schemas de chamadas, prompts de sistema com foco em citação estrita de evidências e tratamento de erros/timeouts.
2. **Harness de Benchmark e Instrumentação:** Coleta estruturada de logs (`ExperimentRun`), rastreabilidade de chamadas (`run_id`), medição de tokens/latência e conexão com a frente de Metodologia para o pareamento experimental com o LangGraph.

Limites: Não instalar um homônimo sem auditar a fonte. Não duplicar ferramentas de negócio ou acessar o banco diretamente (usar sempre `ToolClient`). Não alterar schemas de contratos sem alinhamento com Backend.

As definições OpenAI/ChatML das três ferramentas de leitura ficam em `agents/hermes/tools.py` e derivam seus parâmetros dos modelos de entrada em `contracts/models.py`.

## Entradas, saídas e dependências

Recebe tarefa, ToolContext, endpoint/modelo aprovados e API; entregará resultado e ExperimentRun rastreável.

Coordenação confirma Hermes; Backend fornece ferramentas; Infra fornece configuração; Metodologia define limites/métricas e revisão cruzada com LangGraph.

Pastas: agents/hermes/; agents/interface.py é compartilhado e exige revisão da outra equipe.

## Estudar e executar

Documentação oficial do Hermes confirmado, tool calling, HTTP, timeouts, estado, encerramento e instrumentação.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo para popular a base sintética. Em outro terminal, inicie a API com `uv run --locked python -m scripts.dev serve`. Com a API local ativa em `http://127.0.0.1:8000`, configure `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY` no terminal do agente e execute uma tarefa de avaliação:

```sh
uv run --locked python -m agents.hermes.run --task-id DEV-001
```

O comando lê a tarefa de `evaluation/tasks.json`, chama `HermesAdapter` com o contexto dessa tarefa e imprime a resposta final e o `ExperimentRun` em JSON. O adapter usa `http://127.0.0.1:8000` para as ferramentas. A chamada à LLM usa o endpoint e as credenciais configurados no ambiente; o smoke `uv run --locked python -m agents.smoke --adapter hermes` continua testando apenas a interface HTTP, sem executar o agente real.

## Primeiras tarefas

1. **Definição de Runtime e Dependências:** Fixar repositório/pacote oficial (Nous Research / Hermes Tool Calling), licença e travar no `pyproject.toml`.
2. **Loop de Tool Calling e Adapters:** Implementar `HermesAdapter(AgentAdapter)` conectando o loop autônomo ao `ToolClient` para consumir as ferramentas de leitura (`consultar_processo`, `buscar_documentos`, `ler_documento`).
3. **Engenharia de Prompt e Regras SEI:** Desenvolver o System Prompt orientando o agente a citar evidências físicas (processo, documento e página), respeitar limitações de bases parciais e não inventar fatos em buscas vazias.
4. **Instrumentação e Coleta para Benchmark:** Estruturar a geração de `ExperimentRun` (tokens, latência, histórico de chamadas e controle rígido por `run_id`).

## Critério de conclusão

Agente Hermes funcional resolvendo tarefas sintéticas e reais via chamadas ao backend, com exportação de `ExperimentRun` auditável e pronta para execução no harness pareado de benchmark. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

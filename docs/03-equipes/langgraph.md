# LangGraph

Integrantes: 1 | Monitor: João Enomoto. Branch: `team/langgraph`.

- **Monitor:** João Enomoto
- **Integrantes:**
  - Igor Razzi*

## Objetivo e responsabilidades

Preparar execução por grafo com estado e seleção dinâmica de ferramentas comparável ao Hermes.

Estado, nós, transições condicionais, limites de chamadas/tempo, encerramento e registros. Documentar decisões do adaptador.

Limites: Não impor sequência fixa que resolva previamente tarefas do benchmark. Não implementar ferramenta de negócio no grafo nem acessar banco diretamente.

## Entradas, saídas e dependências

Recebe tarefa, contexto, API e configuração de modelo; entregará resultado e ExperimentRun no mesmo formato do Hermes.

Backend fornece tools; Metodologia define orçamento/rubricas; Infra define execução; Hermes participa da revisão de equivalência.

Pastas: agents/langgraph/; agents/interface.py compartilhado.

## Estudar e executar

LangGraph oficial, mensagens, estado, grafos, tool calling, arestas condicionais, limites e checkpoints.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m agents.smoke --adapter langgraph
```

Pré-requisito: demo executada e API em outro terminal com `uv run --locked python -m scripts.dev serve`. O comando testa só HTTP; não executa o agente real.

## Primeiras tarefas

1. Executar smoke com API local populada; identificar diferença para integração real.
2. Propor estado e ciclo modelo → solicitação de ferramenta → backend → retorno ao modelo → nova decisão/encerramento.
3. Escolher versão em ADR e preparar teste de parada por orçamento antes de integrar o modelo externo.

## Critério de conclusão

Interface exercitada, estado/limites revisados e plano dinâmico de integração sem solução pré-programada das tarefas. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

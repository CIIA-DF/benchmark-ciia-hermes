# Hermes

Pessoas propostas: 2. Branch: `team/hermes`.
Responsável nominal: **a preencher**. Integrantes: **a preencher**. Revisor: **a preencher**.

## Objetivo e responsabilidades

Integrar o executor Hermes aprovado às ferramentas e ao protocolo comum.

Confirmar produto/repositório/versão/licença, documentar extensão de ferramentas, limites, prompts internos e registros do executor.

Limites: Não instalar um homônimo nem inventar APIs. Não duplicar ferramentas ou acessar o banco diretamente. Não implementar agente completo nesta base inicial.

## Entradas, saídas e dependências

Recebe tarefa, ToolContext, endpoint/modelo aprovados e API; entregará resultado e ExperimentRun rastreável.

Coordenação confirma Hermes; Backend fornece ferramentas; Infra fornece configuração; Metodologia define limites/métricas e revisão cruzada com LangGraph.

Pastas: agents/hermes/; agents/interface.py é compartilhado e exige revisão da outra equipe.

## Estudar e executar

Documentação oficial do Hermes confirmado, tool calling, HTTP, timeouts, estado, encerramento e instrumentação.

Primeiro siga [instalação](../getting-started.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m agents.smoke --adapter hermes
```

Pré-requisito: demo executada e API em outro terminal com `uv run --locked python -m scripts.dev serve`. O comando testa só HTTP; não executa o agente real.

## Primeiras tarefas

1. Registrar URL oficial, versão/commit, licença e API de extensão em decisão; critério: outro integrante consegue verificar a fonte.
2. Com API local populada em execução, executar o smoke; registrar que não é integração real.
3. Mapear uma ferramenta ao contrato comum em proposta revisada, incluindo timeout e tradução de erros.

## Critério de conclusão

Identidade do Hermes comprovada e primeira chamada rastreável sem ferramenta duplicada; integração real só pode ser declarada após teste do executor aprovado. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../backlog.md) · [Git](../git-workflow.md) · [Contratos](../../contracts/README.md)

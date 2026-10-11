# Metodologia e avaliação (Evaluation)

Integrantes: 5 | Monitor: Gustavo Antônio. Branch: `team/metodologia`.

- **Monitor:** Gustavo Antônio
- **Integrantes:**
  - Nelson da Rocha Bomfim Neto (3° semestre eng. de software)
  - Hugo Coelho Teixeira (3° semestre eng. de software)
  - Sarah Leticia da Silva (3° semestre de sistemas de informação)
  - João Pedro Silva dos Santos (5° semestre eng. de software)
  - Isaac Joaquim (5° semestre eng. de software)

## Objetivo e responsabilidades

Definir tarefas, rubricas e métricas antes da coleta e produzir comparação reproduzível.

Desenho pareado, desenvolvimento versus avaliação final, gabaritos, evidências, métricas, análise de incerteza/erros e rastreabilidade do harness.

Limites: Não inventar resultados nem ajustar rubrica depois de ver vencedores. Não considerar sucesso declarado como escrita confirmada ou repetições como observações independentes.

## Entradas, saídas e dependências

Recebe corpus/versões e registros dos executores; entrega protocolo pré-definido, tarefas e critérios, depois análise baseada em evidências reais.

Documentos valida fontes; Backend comprova persistência; agentes instrumentam chamadas; Infra mede ambiente; Coordenação decide corpus, especialista e veículo.

Pastas: evaluation/, contratos de ExperimentRun em revisão conjunta, documentação científica.

## Estudar e executar

Desenho experimental pareado, rubricas, avaliação cega, unidades de análise, medidas repetidas, latência/tokens/custo e análise de erros.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev check
```

Use `uv run --locked python -m scripts.dev check` antes do PR.

## Primeiras tarefas

1. Revisar a tarefa sintética de desenvolvimento em evaluation/tasks.json.
2. Escrever mais duas tarefas com resultado observável, fontes e rubrica antes de executar agentes.
3. Definir plano de amostragem/repetições e reconciliar 360 versus 1.080 execuções dos PDFs com a coordenação.

## Critério de conclusão

Tarefas/rubricas versionadas antes da coleta, conjuntos separados, versões congeláveis e regra explícita de confirmação de resultado. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

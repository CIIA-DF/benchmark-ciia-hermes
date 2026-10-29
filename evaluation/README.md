# Metodologia e avaliação

Estado: protocolo inicial e tarefa sintética de desenvolvimento; **nenhuma execução comparativa nem resultado científico coletado**.

Leia [protocolo](protocol.md), [tarefas](tasks.json), [contrato de registro](../contracts/models.py) e [guia da equipe](../docs/03-equipes/metodologia.md). Rode `uv run --locked python -m scripts.dev check` para validar o exemplo e contratos. A demonstração técnica não é experimento com agentes.

## Validar o pipeline em simulação

O runner atual aceita somente `simulation`; Hermes e LangGraph ainda não têm adaptadores executáveis. No terminal, na raiz do repositório:

```sh
uv run --locked python -m evaluation.runner --adapter simulation
uv run --locked python -m evaluation.metrics
```

A simulação grava registros em `evaluation/results/`, sem chamar ferramentas ou agentes. Ela define `verified_success` e custos como desconhecidos; portanto, não produz taxa de sucesso ou custo científico. Use-a apenas para verificar a leitura do catálogo, a validação do contrato e a gravação/resumo de registros.

Próxima entrega: tarefas/rubricas aprovadas pelo especialista de domínio, divisão desenvolvimento/final e definição de tamanho amostral/unidade de análise antes da coleta.

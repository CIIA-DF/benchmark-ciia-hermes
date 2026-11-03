# Metodologia e avaliação

Estado: protocolo inicial, catálogo com 15 tarefas sintéticas piloto (`DEV-001` a `DEV-015`), rubricas factuais homologadas, protocolo de avaliação cega e runner de simulação com pareamento; **nenhuma execução comparativa com agentes reais nem resultado científico coletado**.

Leia [protocolo](protocol.md), [gabaritos homologados](gabaritos.md), [avaliação cega](blind_review.md), [formulário de avaliação](formulario_avaliacao_cega.md), [tarefas](tasks.json), [rubrica](rubric.py), [contrato de registro](../contracts/models.py) e [guia da equipe](../docs/03-equipes/metodologia.md). Rode `uv run --locked python -m scripts.dev check` para validar o exemplo e contratos. A demonstração técnica não é experimento com agentes.

## Validar o pipeline em simulação

O runner de linha de comando executa `simulation` por padrão; a função `run_paired_adapters` executa adaptadores em pareamento contrabalanceado quando disponíveis. No terminal, na raiz do repositório:

```sh
uv run --locked python -m evaluation.runner --adapter simulation
uv run --locked python -m evaluation.metrics
```

A simulação grava registros em `evaluation/results/`, sem chamar ferramentas ou agentes. Ela define `verified_success` e custos como desconhecidos; portanto, não produz taxa de sucesso ou custo científico. Use-a apenas para verificar a leitura do catálogo, a validação do contrato e a gravação/resumo de registros.

Próxima entrega: tarefas finais reservadas fora do Git aprovadas pelo especialista de domínio e congelamento pré-coleta.

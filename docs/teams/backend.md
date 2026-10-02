# Backend e ferramentas

Pessoas propostas: 3. Branch: `team/backend`.
Responsável nominal: **a preencher**. Integrantes: **a preencher**. Revisor: **a preencher**.

## Objetivo e responsabilidades

Oferecer as mesmas ferramentas confiáveis aos dois agentes.

API, persistência, validação, filtros por processo/corpus e futuras operações autorizadas. Backend executa; agentes selecionam.

Limites: Não escolher política de raciocínio dos agentes nem avaliar sozinho qualidade da extração. Escrever somente no ambiente experimental, após implementar autorização e idempotência.

## Entradas, saídas e dependências

Recebe corpus/contratos e chamadas estruturadas; entrega resultados com fontes, erros seguros e, no futuro, recibos confirmados de persistência.

Documentos prepara corpus; Metodologia define requisitos e observações; Infra fornece banco/configuração; agentes validam consumo da API.

Pastas: services/backend/, tests/backend/, tests/integration/; contracts/ em revisão conjunta.

## Estudar e executar

HTTP, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, transações, constraints, autorização e idempotência.

Primeiro siga [instalação](../getting-started.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev test-backend
```

Use `uv run --locked python -m scripts.dev check` antes do PR.

## Primeiras tarefas

1. Executar demo e conferir consulta, busca e leitura no /docs.
2. Revisar o teste de leitura entre processos e propor o primeiro caso de autorização por usuário/execução.
3. Propor persistência idempotente de pendência com unique constraint e teste de repetição; implementar só depois de revisar autorização/evidências.

## Critério de conclusão

Entradas inválidas rejeitadas, processo/corpus isolados, saída aderente ao contrato e testes de sucesso/falha com persistência comprovada quando houver escrita. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../backlog.md) · [Git](../git-workflow.md) · [Contratos](../../contracts/README.md)

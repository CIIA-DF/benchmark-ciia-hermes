# Backend e ferramentas (BACK)

Integrantes: 1 | Monitor: Roger Quinelato. Branch: `team/backend`.

- **Monitor:** Roger Quinelato
- **Integrantes:**
  - Letícia Pires de Oliveira (3° semestre eng. de software)

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

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev test-backend
```

Use `uv run --locked python -m scripts.dev check` antes do PR.

## Entrega local e próximas integrações

[PRD](../02-arquitetura/backend-prd.md), [TDD](../02-arquitetura/backend-tdd.md),
[referência da API](../02-arquitetura/backend-api.md) e [handoff dos agentes](../04-operacoes/integracao-agentes.md) descrevem a entrega.
Demonstração das seis tools: `uv run --locked python -m scripts.tools_demo`.

## Primeiras tarefas (histórico v0.1)

Implementação v0.2: [chat e operação](../04-operacoes/chat.md),
contratos de workers, migrações e ferramentas estão disponíveis para revisão.
Próximo aceite conjunto: conectar cada adaptador real, homologar os
checklists e conferir a execução em PostgreSQL e na infraestrutura aprovada.
As tarefas abaixo preservam o onboarding da base v0.1.

1. Executar demo e conferir consulta, busca e leitura no /docs.
2. Revisar o teste de leitura entre processos e propor o primeiro caso de autorização por usuário/execução.
3. Propor persistência idempotente de pendência com unique constraint e teste de repetição; implementar só depois de revisar autorização/evidências.

## Critério de conclusão

Entradas inválidas rejeitadas, processo/corpus isolados, saída aderente ao contrato e testes de sucesso/falha com persistência comprovada quando houver escrita. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

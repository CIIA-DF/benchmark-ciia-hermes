# Infraestrutura

Pessoas propostas: 2. Branch: `team/infra`.
Responsável nominal: **a preencher**. Integrantes: **a preencher**. Revisor: **a preencher**.

## Objetivo e responsabilidades

Manter execução reproduzível, configuração, persistência e monitoramento do ambiente experimental.

Compose, versões, volumes, saúde, logs seguros, backups/restauração, CI e apoio ao fluxo Git manual das equipes. Preparar VPS com autorização.

Limites: Não implantar nem promover production por iniciativa própria. Não administrar qualidade do corpus ou rubricas; não presumir SSH, domínio, credenciais ou GPU.

## Entradas, saídas e dependências

Recebe versão aprovada e configuração; entrega serviços saudáveis, evidência de persistência, procedimentos de recuperação e registros operacionais sem conteúdo sensível.

Coordenação libera acessos e aprova versões; Backend define banco/migrações; equipes informam comandos/necessidades; Metodologia define medições.

Pastas: infra/, .github/workflows/ci.yml, scripts/validate_repository.py, docs/runbooks/.

## Estudar e executar

Linux/SSH, Docker Compose, redes, volumes, PostgreSQL backup, GitHub Actions, revisão, rulesets e menor privilégio.

Primeiro siga [instalação](../getting-started.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev up
```

Pré-requisito: Docker Compose e .env com senha. Depois rode `uv run --locked python -m scripts.dev demo-compose`. Sem Docker, registre a limitação e execute `uv run --locked python -m scripts.dev check`.

## Primeiras tarefas

1. Executar up e demo-compose com senha local; reiniciar serviços e conferir dados sem reinserir.
2. Exercitar backup/restauração em banco separado e registrar comparação.
3. Conferir checks e regras de revisão após autorização; orientar a equipe a incorporar main manualmente antes das tarefas e das entregas, preservando os commits.

## Critério de conclusão

Comandos reproduzíveis, healthchecks aprovados, persistência/recuperação demonstradas e nenhum serviço sensível publicado por padrão. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../backlog.md) · [Git](../git-workflow.md) · [Contratos](../../contracts/README.md)

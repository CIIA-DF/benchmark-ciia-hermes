# Regras operacionais

Objetivo: comparar Hermes e LangGraph sobre exportações manuais do SEI, somente em ambiente experimental.
Leia `docs/architecture.md`, `contracts/README.md` e `docs/teams/<equipe>.md` da tarefa.
Identifique equipe pela tarefa e branch (`git status --short --branch`); delimite pastas antes de editar.

- Instalação: `uv sync --locked` (Python 3.12, lock versionado).
- Demo: `uv run --locked python -m scripts.dev demo`.
- Verificação: `uv run --locked python -m scripts.dev check`.
- Testes dirigidos: `uv run --locked python -m scripts.dev test-backend`, `test-documents` ou `test-integration`.
- Fluxo: tarefa opcional → `team/*` → PR para `main` → PR aprovado pela coordenação para `production`.
- Antes de iniciar tarefas e antes do PR para `main`, a equipe coordena a incorporação manual de `origin/main` por merge; siga `docs/git-workflow.md`. Atualizar `main` não abre PRs nem modifica branches de equipe automaticamente.
- Use merge commits nas branches permanentes; nunca force push, exclusão automática ou rebase/squash nesse fluxo.
- Preserve alterações locais. Não apague histórico nem sobrescreva trabalho ao sincronizar.
- Contratos/ferramentas: explicite mudanças em issue/PR, atualize consumidores/testes e solicite revisão das equipes afetadas.
- Não invente APIs, dependências ou capacidades do Hermes. URL e versão estão pendentes.
- Não remova verificações para esconder falhas nem declare sucesso sem evidência.
- Não insira documentos reais, credenciais ou conteúdo sensível em fixtures, código e logs.
- Não implante nem promova para `production` por iniciativa própria.
- Restrinja o diff à tarefa; não refatore/reformate todo o projeto numa mudança pequena.

Entrega: comportamento reproduzível, testes pertinentes, contratos/docs coerentes e diff revisado.
Informe comandos, resultados, limitações e verificações não realizadas com motivo.
Guias de equipe são leitura explícita para ambas as ferramentas; não dependem de descoberta automática.
Markdown orienta; permissões, revisão e CI impõem controles técnicos.

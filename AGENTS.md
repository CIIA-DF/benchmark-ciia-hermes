# Regras operacionais

Objetivo: comparar Hermes e LangGraph sobre exportações manuais do SEI, somente em ambiente experimental.
Leia `docs/02-arquitetura/architecture.md`, `contracts/README.md` e o guia da equipe em `docs/03-equipes/` (Backend: `backend.md`).
Identifique equipe pela tarefa e branch (`git status --short --branch`); delimite pastas antes de editar.

- Instalação: `uv sync --locked` (Python 3.12, lock versionado).
- Demo: `uv run --locked python -m scripts.dev demo`.
- Verificação: `uv run --locked python -m scripts.dev check`.
- Testes dirigidos: `uv run --locked python -m scripts.dev test-backend`, `test-documents` ou `test-integration`.
- Fluxo: tarefa opcional → `team/*` → PR para `main` → PR aprovado pela coordenação para `production`.
- Antes de iniciar tarefas e antes do PR para `main`, a equipe coordena a incorporação manual de `origin/main` por merge; siga `docs/00-comece-aqui/02-fluxo-git.md`. Atualizar `main` não abre PRs nem modifica branches de equipe automaticamente.
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

## Continuidade de Backend & Tools

- Consolidação local de 25/10/2026: as conversas de implementação e auditoria usam esta mesma worktree `team/backend`, com diretório explícito nos comandos. `D:\benchmark-ciia-hermes` permanece preservado como cópia anterior; seu estado não representa a entrega atual. Coordene edições simultâneas dos mesmos arquivos e valide as correções aqui, sem replicá-las entre checkouts.

- Worktree desta entrega: `C:\Users\roger\.codex\worktrees\backend-tools\benchmark-ciia-hermes`, branch `team/backend`. Confirme diretório e branch antes de editar; preserve também o trabalho do checkout `D:\benchmark-ciia-hermes`.
- Autorização atual: trabalho local. Commits de implementação, push, PR e publicação dependem de solicitação posterior do responsável.
- Antes de continuar features, leia `docs/02-arquitetura/backend-prd.md`, `docs/02-arquitetura/backend-tdd.md` e as decisões em `docs/05-decisoes/README.md`.
- Escopo: seis tools, API de consumo, memória do chat e interface de entrada/retorno. Backend executa operações; agentes selecionam ferramentas. Documentos/RAG mantém ingestão e corpus; as equipes Hermes/LangGraph fornecem adaptadores reais.
- Pastas da frente: `services/backend/`, `tests/backend/`, `tests/integration/`, `migrations/`, `scripts/` e documentação de backend. Alterações em `contracts/` e `agents/` exigem coerência entre consumidores. Para o chat em `portal/`, leia antes `portal/AGENTS.md`.
- Para executar o chat e conferir recibos, siga `docs/04-operacoes/chat.md`. Para conectar agentes reais, siga `docs/04-operacoes/integracao-agentes.md`; o simulador e doubles de teste não comprovam inferência real.
- Evidências da entrega de 24/10/2026: `docs/04-operacoes/validacao-backend-2026-10-24.md`. Consulte esse registro antes de reutilizar resultados; mudanças posteriores exigem verificações pertinentes. Inspeção visual nesta rodada e homologação dos runtimes reais permanecem pendentes.

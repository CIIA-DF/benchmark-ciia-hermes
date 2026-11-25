# Registro de Decisões de Arquitetura (ADRs)

| ADR | Título | Equipe | Situação |
| --- | --- | --- | --- |
| [001](001-base-inicial.md) | Base inicial do benchmark e contratos v0.1 | Coordenação | Aprovada |
| [002](002-atualizacao-manual-equipes.md) | Atualização manual das branches de equipe | Coordenação | Aprovada |

> [!NOTE]
> **Resolução de Numeração para PRs em Andamento**:
> - A equipe de **Metodologia / Avaliação** propôs o uso do provedor de inferência OpenRouter e benchmark em duas camadas sob a identificação `003-provedor-inferencia-openrouter.md`.
> - A equipe de **Backend** desenvolveu propostas técnicas subsequentes para chat, tools e rastreio de orçamento (`003` a `008`).
> - Antes da integração final na branch `main`, a coordenação padroniza a ADR 003 para o Provedor de Inferência/Metodologia e renumera sequencialmente as decisões de Backend a partir de `004`.

Novas decisões devem registrar contexto, escolha, consequências, responsáveis e situação (proposta/aprovada/substituída). Não altere retrospectivamente uma decisão para esconder mudança experimental.

## Backend e chat

- [ADR 003 — chat, tools e execuções](003-chat-tools-execucoes.md).
- [ADR 004 — tools e fronteira RAG](004-tools-fronteira-rag.md).
- [ADR 005 — participante sem login](005-participante-sem-login.md).
- [ADR 006 — integração dos adaptadores](006-integracao-adaptadores.md).
- [ADR 007 — rastreio e orçamento das tools](007-rastreio-orcamento-tools.md) (proposta v0.3).

[PRD](../02-arquitetura/backend-prd.md) · [TDD](../02-arquitetura/backend-tdd.md).

- [ADR 008 — tentativas físicas e fases das tools](008-tentativas-fisicas-tools.md): base F0; preserva ledger legado sem inferir requisições.

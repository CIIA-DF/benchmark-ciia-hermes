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

Renumeração aplicada em 21/11/2026 na `team/backend`, conforme a nota acima: a 003 fica reservada à ADR de provedor de inferência e benchmark em duas camadas (hoje em `team/evaluation`); as decisões do backend passam a começar em 004. Relatórios de validação anteriores citavam os números antigos; os links foram atualizados e o conteúdo das decisões não mudou.

| ADR | Número anterior | Título | Situação |
| --- | --- | --- | --- |
| [004](004-chat-tools-execucoes.md) | 003 | Chat, tools e execuções | Implementada localmente; revisão conjunta pendente |
| [005](005-tools-fronteira-rag.md) | 004 | Tools e fronteira RAG | Implementada localmente; revisão conjunta pendente |
| [006](006-participante-sem-login.md) | 005 | Participante sem login | Decidida pelo responsável; implementada localmente |
| [007](007-integracao-adaptadores.md) | 006 | Integração dos adaptadores | Infraestrutura local; agentes reais pendentes |
| [008](008-rastreio-orcamento-tools.md) | 007 | Rastreio e orçamento das tools (contrato v0.3) | Proposta às equipes; sem aprovação de Hermes, LangGraph e Metodologia |
| [009](009-tentativas-fisicas-tools.md) | 008 | Tentativas físicas e fases das tools; preserva o ledger legado | Implementada localmente; revisão conjunta pendente |
| [010](010-documentacao-interfaces.md) | 009 | Consolidação documental das interfaces | Implementada localmente; aprovação conjunta pendente |
| [011](011-registro-experimental-revisoes.md) | — | Registro experimental com revisões, portado do LangGraph (João Enomoto, `856ff06`) | Implementada localmente; revisão do LangGraph e da Metodologia pendente |

[PRD](../02-arquitetura/backend-prd.md) · [TDD](../02-arquitetura/backend-tdd.md).

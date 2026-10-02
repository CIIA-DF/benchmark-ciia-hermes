# ADR 002 — incorporação manual de main pelas equipes

Data: 30/09/2026. Situação: decisão solicitada pela coordenação e implementada localmente.

Substitui apenas a decisão de propagação automática da main da [ADR 001](001-base-inicial.md). As demais escolhas da base permanecem.

## Decisão

Um único repositório mantém team/documentos, team/backend, team/hermes, team/langgraph, team/infra, team/metodologia, main e production. Cada equipe coordena a incorporação **manual** de origin/main antes de iniciar tarefas e antes de integrar suas entregas.

O responsável salva o trabalho local, faz fetch, atualiza a cópia da equipe e mescla origin/main numa branch curta da equipe. Resolve conflitos, executa verificações e abre manualmente PR para a equipe, respeitando suas proteções. Merge commits preservam a ancestralidade e os commits exclusivos. Nunca reset destrutivo, force push ou exclusão das branches permanentes. Comandos completos no [guia Git](../git-workflow.md).

Fluxo: desenvolvimento na equipe (tarefas curtas opcionais) → PR para main com revisão/checks → testes integrados → PR main para production aprovado pela coordenação/responsável → implantação autorizada na Hostinger. Merge e implantação são etapas distintas; nenhuma automação de implantação foi criada.

## Consequências

Atualizações da main não abrem PRs nem alteram branches das equipes automaticamente. O mecanismo anterior, seus testes exclusivos e suas instruções de ativação foram retirados. CI de validação, testes da aplicação, templates e proteções permanecem.

Cabe à equipe combinar o responsável e o momento de cada atualização; estado remoto e cópia local continuam distintos. Configurações e PRs antigos, se existentes, exigem [conferência administrativa](../runbooks/github-governance.md). Nenhuma alteração remota faz parte desta implementação.

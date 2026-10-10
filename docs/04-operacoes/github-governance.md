# Governança GitHub — ativação administrativa pendente

Nada neste guia foi aplicado ao remoto. Coordenação deve confirmar plano/permissões da organização e nomear administradores/revisores. CODEOWNERS só indica revisores: exigir aprovação depende das regras do GitHub.

## Preparar o repositório

Após revisar/integrar esta base, publicar as seis branches team/* e production a partir do commit main aprovado. Fazer isso como ação administrativa autorizada. Conferir branches existentes antes: nunca substituir uma branch que já contenha trabalho.

Em Settings → General → Pull Requests, habilitar merge commits e desabilitar squash/rebase para este fluxo; desligar **Automatically delete head branches**. Não exigir histórico linear, pois impediria merge commits.

## Rulesets ativos

Configurar rulesets ou proteções equivalentes cobrindo main, production e as seis team/*:

- Require a pull request before merging; ao menos uma aprovação humana, dispensar aprovações antigas quando mudanças relevantes chegarem e exigir resolução das conversas.
- Require status checks: nomes exatos **quality** e **integration**, origem GitHub Actions.
- Bloquear force push (non-fast-forward) e exclusão.
- Manter revisão e checks obrigatórios sem bypass; a coordenação também segue o fluxo.
- Revisão de CODEOWNERS quando o mapa real estiver preenchido.

Primeiro rode a CI para os checks aparecerem na interface; selecione os nomes realmente emitidos (não invente variações). Não use filtros de caminhos que deixem checks obrigatórios sem execução. O workflow cobre PR, push nas permanentes e merge_group; workflow_dispatch é diagnóstico, não substitui check de PR.

A incorporação manual de main passa por uma branch curta baseada na equipe e um PR revisado para essa equipe, conforme o [guia Git](../00-comece-aqui/02-fluxo-git.md). Não há mais exceção de proteção motivada por PRs automáticos com main como origem. Antes do merge, confira se os checks correspondem à versão atual e incorpore mudanças adicionais da base na branch curta quando necessário. Alterações nas proteções remotas continuam sendo ação administrativa autorizada.

Restrinja atualizações de production aos responsáveis nomeados usando regra de restrição de push/atores disponível no plano. Combine-a com regras obrigatórias separadas e sem bypass para revisão/checks; valide efetivamente com conta não autorizada. Quando necessário, use proteção clássica para a restrição de quem pode atualizar production, mantendo os requisitos de PR/CI. A regra de identidade de responsáveis depende das contas reais.

As equipes usam branches curtas e PRs revisados para atualizar suas permanentes. Cada equipe coordena a incorporação manual da main antes das tarefas e das entregas. A CI somente valida: não abre PRs nem modifica branches, e merge não executa implantação.

## Mapa de revisão

Preencher [.github/CODEOWNERS](../../.github/CODEOWNERS) com contas/times reais com acesso de escrita. Mapear contratos aos líderes de Backend, Documentos, ambos agentes e Metodologia; .github a Infra e Coordenação. Não há contas fictícias no modelo.

A exigência de revisão de dono depende da configuração; várias contas numa linha não significam que todas precisam aprovar. Combinar revisão dos consumidores pelo processo de PR para mudanças compartilhadas.

## Conferir os controles de qualidade

Abra PR sintético que falhe um teste: merge deve ficar bloqueado. PR sem revisão deve ficar bloqueado. Force push e exclusão das permanentes devem ser negados. Confirme que apenas responsáveis autorizados podem atualizar production, respeitando revisão e checks. Reexecute CI após qualquer mudança relevante nos rulesets/workflows.

Fontes oficiais consultadas: [checks obrigatórios](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks) e [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).

## Conferência de configurações antigas no GitHub

A consulta pública à API em 30/09/2026 retornou HTTP 404. A leitura via Git (`git ls-remote`) foi possível: anunciou apenas `main` no commit 48ee67223fde1935113aea244d706ae71c24bb5d, sem branches de equipe nem referências de PR. Essa main ainda corresponde à base original, sem o workflow retirado nesta tarefa. Sem acesso autenticado à API nesta sessão, não foi possível inspecionar configurações de Actions, variáveis, secrets ou instalações de Apps; a ausência de referências de PR anunciadas não substitui uma auditoria dos PRs pela interface/API. Nenhuma configuração ou credencial remota foi alterada.

Se a preparação anterior chegou a ser publicada/ativada, um administrador autorizado deve:

1. Conferir se o antigo workflow **Sincronizar equipes** está ativo no GitHub e desativá-lo, incluindo execuções pendentes, até que sua remoção esteja publicada na main.
2. Localizar PRs antigos com head `main`, base `team/*` e título de sincronização; desabilitar o auto-merge desses PRs e encerrar os obsoletos, sem excluir as branches permanentes. A equipe pode depois incorporar main pelo procedimento manual.
3. Inventariar as variáveis antigas `SYNC_ENABLED`, `SYNC_AUTO_MERGE`, `SYNC_APP_ID`, o secret `SYNC_APP_PRIVATE_KEY` e o App antes usado exclusivamente para essa finalidade. Eles não são necessários ao fluxo atual; remoção/revogação depende de autorização e confirmação de que nenhum outro serviço os utiliza.
4. Preservar a CI, seus checks, os templates e as permissões necessárias às outras entregas.

Essas são instruções de desativação e conferência, não de configuração de uma nova automação. Publicar a remoção local não fecha PRs existentes nem revoga credenciais por si só.

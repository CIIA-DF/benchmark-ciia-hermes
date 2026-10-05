# Fluxo Git obrigatório

Branches permanentes: `team/documentos`, `team/backend`, `team/hermes`, `team/langgraph`, `team/infra`, `team/metodologia`, `main` e `production`. Coordenação precisa publicar as ausentes durante a ativação.

## Selecionar sua equipe

Exemplo para Documentos; troque pelo nome da equipe:

```sh
git clone https://github.com/CIIA-DF/benchmark-ciia-hermes.git
cd benchmark-ciia-hermes
git fetch origin
git switch --track origin/team/documentos
git status --short --branch
```

Se já existe localmente: `git switch team/documentos`. Antes de sincronizar, revise `git diff` e salve alterações com commit ou `git stash push -u -m "trabalho em andamento"`; confira `git stash list`. Stash é local, não backup remoto. Não use reset destrutivo para limpar a pasta.

## Atualizar a cópia local da branch da equipe

Com trabalho salvo e na branch correta:

```sh
git fetch origin
git merge --no-edit origin/team/documentos
```

Se usou stash, faça `git stash apply`, confira/teste e só então remova aquela entrada com `git stash drop`. Resolver conflitos também pode ser necessário ao aplicar stash. Atualizar a branch remota nunca atualiza automaticamente os computadores: cada integrante precisa sincronizar.

## Incorporar main manualmente — responsabilidade da equipe

Faça esta atualização **antes de iniciar tarefas e antes de integrar as entregas da equipe em main**. Combine quem realizará o merge para evitar trabalhos paralelos sobre a mesma atualização. Uma mudança em main não abre PRs nem modifica automaticamente as branches das equipes.

Primeiro confira `git status --short --branch`, `git diff` e `git diff --cached`. Salve o trabalho na branch apropriada com commit ou stash antes de trocar de branch. Não use reset destrutivo nem force push. Commits locais não publicados também devem ser revisados para não entrar por engano no PR de atualização.

Exemplo para Documentos, depois de salvar o trabalho:

```sh
git switch team/documentos
git fetch origin
git merge --no-edit origin/team/documentos
git switch -c task/documentos-atualizar-main
git merge --no-ff origin/main
```

Escolha um nome ainda não usado para a branch curta. Fetch atualiza as referências remotas locais sem alterar seus arquivos. O primeiro merge incorpora commits publicados pela equipe; o segundo une a main à linha de trabalho da equipe, preservando os commits de ambos os lados. Use `origin/main`, não uma main local possivelmente desatualizada. Se houver conflito, resolva conforme a seção abaixo antes de continuar.

```sh
uv run --locked python -m scripts.dev check
git diff origin/team/documentos...HEAD
git push -u origin task/documentos-atualizar-main
```

O responsável abre **manualmente** PR dessa branch curta para `team/documentos`, aguarda revisão e checks e incorpora por **Create a merge commit**. Essa rota respeita as proteções da branch; não exige push direto nela. Se main já estiver incorporada e não houver nenhuma outra mudança, não há PR a abrir.

Após o merge do PR, todos atualizam a própria cópia:

```sh
git switch team/documentos
git fetch origin
git merge --no-edit origin/team/documentos
```

Reaplique o stash na branch de trabalho apropriada, confira/teste e só então remova a entrada salva. Uma tarefa curta já em andamento pode incorporar `origin/team/documentos` com merge para receber a atualização, também sem rebase.

Antes do PR da equipe para main, busque novamente o estado remoto. Se a main avançou, repita a incorporação manual e as verificações. Nenhuma dessas atualizações altera main ou production por conta própria.

## Trabalhar e abrir PR

Opcionalmente, crie `git switch -c task/documentos-evidencias` a partir da equipe. Faça a tarefa e rode verificações:

```sh
git diff
git add caminho/do/arquivo
git commit -m "Preserva a página de origem"
git push -u origin task/documentos-evidencias
```

No GitHub: Pull requests → New pull request. Base = `team/documentos`; compare = branch curta. Preencha template, aguarde checks e revisão, incorpore por **Create a merge commit**. Para integrar a equipe, abra outro PR com base `main`, compare `team/documentos`.

Fluxo: tarefa opcional → equipe → PR/revisão → main → verificação integrada → PR aprovado por André/Gustavo/João Enomoto ou delegado → production → implantação autorizada. Merge/promover código e implantar são etapas distintas: aprovar o PR não coloca serviços em execução na Hostinger. A implantação segue o [runbook autorizado](runbooks/hostinger-deploy.md); esta mudança de fluxo não cria automação de implantação. production é estável experimental.

## Push rejeitado

Leia a mensagem: pode haver commits novos ou proteção. Salve trabalho, faça fetch e merge da própria branch remota, teste e tente push novamente. Se a causa for proteção, siga o PR exigido. Nunca force push.

## Conflitos e recuperação

`git status` identifica arquivos em conflito. Abra-os, combine o conteúdo correto com o outro autor, remova marcadores <<<<<<<, =======, >>>>>>>, teste, use `git add arquivo` e `git commit`. Não aceite tudo de um lado indiscriminadamente. Para desistir do merge em andamento: `git merge --abort`; peça apoio com o diff.

Ao incorporar main manualmente, resolva conflitos na branch curta criada a partir da equipe e submeta o resultado à revisão da equipe. Não leve trabalho incompleto da equipe para main apenas para resolver esse conflito.

Commit incorreto já compartilhado: numa branch de correção, use `git revert SHA_DO_COMMIT`, teste e abra PR. É um novo commit que desfaz a mudança. Reverter merge exige revisão do responsável sobre o pai escolhido com -m. Evite amend/rebase em commits compartilhados; para erro local, outro commit simples também serve.

Merge commits preservam os pais e permitem reconhecer integrações anteriores nos dois sentidos main ↔ equipe. Squash perde ancestralidade; rebase reescreve IDs. Neste fluxo permanente, ambos podem causar diffs repetidos e conflitos. Use merge commits também para main → production.

Force push e exclusão automática das branches permanentes são proibidos. Branch curta só pode ser removida depois da integração confirmada. Veja [governança](runbooks/github-governance.md).

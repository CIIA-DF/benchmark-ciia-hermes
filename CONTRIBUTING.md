# Contribuir com uma primeira tarefa

1. Leia [início rápido](docs/00-comece-aqui/01-inicio-rapido.md), [glossário](docs/00-comece-aqui/03-glossario.md) e seu [guia de equipe](docs/00-comece-aqui/04-equipes.md).
2. Escolha tarefa pequena do [backlog](docs/01-overview/backlog.md), registre responsável/revisor e use template de issue.
3. Antes de iniciar a tarefa, combine com a equipe a incorporação manual da main conforme o [fluxo Git](docs/00-comece-aqui/02-fluxo-git.md), preservando alterações locais e commits.
4. Execute a demo antes de editar. Faça a menor mudança que atende aos critérios.
5. Rode testes pertinentes e `uv run --locked python -m scripts.dev check`. Confira `git diff` e `git status`.
6. Antes do PR da equipe para main, confira novamente se main avançou; incorpore as mudanças manualmente e repita as verificações. Abra PR para a branch correta, preencha o template e peça revisão humana.

IA é opcional. Quem usar continua responsável pelo diff, verificação e explicação; veja [desenvolvimento assistido](docs/02-arquitetura/ai-development.md). Documentação e comentários explicativos em português brasileiro; identificadores podem usar inglês.

Contratos afetam várias frentes: descreva versão, compatibilidade, consumidores, migração e exemplos antes da integração. Atualize `contracts/models.py` e o guia juntos. Dependências ficam em `pyproject.toml` e `uv.lock`; use `uv lock` intencionalmente, revisando o diff. Instalação e CI usam `--locked`.

Não versionar dados reais, `.env`, backups, logs de conteúdo ou chaves. `.gitignore` não substitui revisão. Relate falhas com dados sintéticos reproduzíveis.

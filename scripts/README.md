# Comandos auxiliares

Executar na raiz via `uv run --locked python -m scripts.NOME`.

- dev: setup/up/down/demo/demo-compose/check/test-backend/test-documents/test-integration/serve.
- demo: ingestão fictícia e consulta pela API; --url consulta HTTP já populado; --seed-only somente ingere.
- database_backup: backup FILE ou restore-test FILE; exige Compose, preserva original e cria banco novo para restauração.
- validate_repository: links Markdown locais, YAML e invariantes de CI/Compose; não executa workflows remotos.

Scripts não publicam branches nem implantam como parte do check. A incorporação da main é uma ação manual coordenada pela equipe, conforme o [fluxo Git](../docs/git-workflow.md).

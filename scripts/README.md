# Comandos auxiliares

Executar na raiz via `uv run --locked python -m scripts.NOME`.

- dev: setup/up/down/demo/demo-compose/check/test-backend/test-documents/test-integration/serve.
- demo: ingestão fictícia e consulta pela API; --url consulta HTTP já populado; --seed-only somente ingere.
- database_backup: backup FILE ou restore-test FILE; exige Compose, preserva original e cria banco novo para restauração.
- validate_repository: links Markdown locais, YAML e invariantes de CI/Compose; não executa workflows remotos.

Scripts não publicam branches nem implantam como parte do check. A incorporação da main é uma ação manual coordenada pela equipe, conforme o [fluxo Git](../docs/00-comece-aqui/02-fluxo-git.md).


## Backend e chat v0.2

- tools_demo: prova local das seis ferramentas, incluindo replay e hash de escritas.
- chat: setup/serve/worker/verify/up/down do piloto com credenciais fora do Git.
- provision: configuração administrativa de identidades técnicas e concessões.
- checklist: importação imutável de requisitos versionados.
- migrate: upgrade/downgrade explícitos de schema; downgrade pode apagar dados.
- export_chat: exportação JSONL privada, sem textos por padrão.
- export_openapi: grava services/backend/openapi.yaml a partir da aplicação; --check só confere.

Consulte [operação do chat](../docs/04-operacoes/chat.md) para os comandos completos.

- audit_backend: diagnóstico da [auditoria de 28/10/2026](../docs/04-operacoes/auditoria-backend-2026-10-28.md), apenas com SQLite temporário/dados fictícios; saída zero indica execução, não aceite de segurança.

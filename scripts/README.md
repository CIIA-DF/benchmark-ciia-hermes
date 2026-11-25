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
- export_chat: exportação canônica JSONL v2; chat por padrão, --kind benchmark/all, filtros por participante/conversa/run e conteúdo opt-in. [Formato e migração](../docs/04-operacoes/exportacao-canonica.md).
- benchmark_batch: cria runs de benchmark em lote (tarefa × executor × repetição) a partir de um arquivo no formato `evaluation/tasks.json`; só o `prompt` vai para o agente. Chave de idempotência `rotulo:tarefa:executor:repeticao` (rótulo, `task_id` e executor sem `:`, para que chaves de combinações diferentes não colidam), ordem intercalada e contrabalançada entre executores (`position` no manifesto) e janela `--window` de runs não terminais (a fila tem cota e expira em `RUN_QUEUE_TIMEOUT_SECONDS`). Repete erro de transporte e 5xx `retryable` com espera crescente e só desiste sem progresso por `--stall-seconds` (padrão 1200). Escreve manifesto JSONL; se parar, lista os itens não enviados como `not_submitted`, e rodar de novo com o mesmo rótulo retoma sem duplicar; `--dry-run` só mostra o plano. Exige `BACKEND_OPERATOR_TOKEN`.
- export_openapi: grava services/backend/openapi.yaml a partir da aplicação; --check só confere.

Consulte [operação do chat](../docs/04-operacoes/chat.md) para os comandos completos.

- audit_backend: diagnóstico da [auditoria de 28/10/2026](../docs/04-operacoes/auditoria-backend-2026-10-28.md), apenas com SQLite temporário/dados fictícios; saída zero indica execução, não aceite de segurança. Observação `false` indica achado que não se reproduz mais (ex.: `bootstrap_restores_local_write_and_grant`, achado 05, corrigido no I2); o relatório de 28/10 continua como registro datado.

## Provisionamento explícito — I2

scripts.provision FILE cria por padrão; perfil existente exige --operation update ou --operation rotate.
Update usa configuração completa e substitui permissões; rotate aceita apenas principal_id/token_env e preserva o perfil atual.
Bootstrap nunca atualiza identidades existentes. [Operação e exemplos](../docs/04-operacoes/chat.md#perfis-e-permissões).

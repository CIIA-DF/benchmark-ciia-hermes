# Backup e restauração

Procedimento preparado para Compose; requer Docker e banco em execução. Artefatos ficam fora do Git. Definir responsável, frequência (sugestão inicial: antes de cada implantação e diariamente durante coleta), retenção, destino externo criptografado e teste periódico antes de usar dados reais.

## Criar e testar uma cópia

Na raiz, escolha nome novo para cada backup:

```sh
uv run --locked python -m scripts.database_backup backup backups/piloto-2026-09-29.dump
uv run --locked python -m scripts.database_backup restore-test backups/piloto-2026-09-29.dump
```

O script usa pg_dump em formato custom e fluxo binário, inclusive no PowerShell. Recusa sobrescrever arquivo existente. A restauração cria banco novo restore_check_<id>, restaura com pg_restore --exit-on-error e consulta contagens de processos/documentos/chunks. Original e volume permanecem intactos.

Compare as contagens com o banco original no mesmo instante lógico, examine amostra de hashes/referências e conecte uma instância isolada do backend à cópia para validar consultas. Contagem sozinha não comprova integridade semântica. Registre data, versão PostgreSQL, commit/schema, hash do dump, duração, tamanho e resultado do teste. Mantenha .env/chaves fora do dump e com backup privado separado.

Falha pode deixar arquivo parcial ou banco de teste; o script sinaliza isso. Não considere a cópia válida até restaurar com sucesso. O script não remove bancos de teste automaticamente: após inspeção, Infra deve identificar nome exato e autorizar sua limpeza; nunca apontar essa limpeza ao banco original.

## Recuperação real

Parar gravações/agentes; preservar backup do estado atual; restaurar em banco novo; confirmar compatibilidade de schema/versão; executar saúde e consultas; só então, com autorização, apontar serviços para a cópia. Não restaurar por cima do banco ativo. Registrar perda potencial de dados desde o backup e coordenar reexecução experimental.

Scripts foram preparados localmente; execução contra PostgreSQL/Compose precisa de ambiente Docker. [pg_dump oficial](https://www.postgresql.org/docs/17/app-pgdump.html) e [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

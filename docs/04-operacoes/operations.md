# Operação de desenvolvimento

Na raiz, após configurar .env:

```sh
docker compose --env-file .env -f infra/compose.yml ps
docker compose --env-file .env -f infra/compose.yml logs --tail 100 backend
docker compose --env-file .env -f infra/compose.yml restart backend
```

Saúde: GET http://127.0.0.1:8000/health faz SELECT 1. PostgreSQL usa pg_isready; backend aguarda banco saudável pelo Compose. [Comportamento oficial](https://docs.docker.com/compose/how-tos/startup-order/).

Para demonstrar persistência: rode demo-compose, reinicie serviços, depois `uv run --locked python -m scripts.demo --url http://127.0.0.1:8000` sem seed. Confira referências. Volume postgres_data permanece após down. Nunca remover volume para corrigir falha desconhecida.

Senha do PostgreSQL só inicializa volume novo; editar .env não troca automaticamente senha de banco existente. Use procedimento SQL administrativo autorizado ou restaure em instância separada. Não registrar senha em issue.

Logs operacionais: IDs de execução, componentes, duração, status e versão; sem corpo de documentos, prompts completos, Authorization, chaves e DSNs. Nesta base há apenas healthcheck e log seguro de falha de armazenamento; tracing completo é pendente. Dados de avaliação brutos ficam em armazenamento privado aprovado.

Antes de ativar corpus real: combinar retenção/acessos, autenticação/autorização e auditoria. Monitore disco, espaço para backup, memória, reinícios, duração de consultas e disponibilidade. Defina limiares após medir a carga; números dos PDFs não são medições.

Para problemas de SQL/schema, não editar banco manualmente sem decisão registrada. create_all não migra estruturas. Consulte [backup](backup-restore.md) e [implantação](deploy-vps-hostinger.md).

# Infraestrutura inicial

[compose.yml](compose.yml) sobe PostgreSQL 17 e backend, com volume persistente, healthchecks e API em loopback. Banco não publica portas. [Dockerfile](Dockerfile) usa Python 3.12, uv fixado e aplicação sem usuário root.

Na raiz: copie .env.example, defina senha e execute `uv run --locked python -m scripts.dev up`, depois `demo-compose`. `down` preserva volume. [Início rápido](../docs/getting-started.md).

Imagens têm tags; congelar digests e confirmar arquitetura/plataforma antes dos experimentos finais. Não há GPU, LLM ou acesso à VPS pressupostos.

[Operação](../docs/runbooks/operations.md) · [Backup](../docs/runbooks/backup-restore.md) · [Hostinger/rollback](../docs/runbooks/hostinger-deploy.md) · [Guia da equipe](../docs/teams/infra.md).

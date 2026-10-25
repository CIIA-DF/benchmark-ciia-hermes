# Infraestrutura inicial

A composição v0.2 inclui portal e worker simulado, além de PostgreSQL 17 e
backend. Use [executar o chat](../docs/04-operacoes/chat.md) para gerar senha
e tokens locais e iniciar a stack isolada. O perfil Compose `proxy` permite
conferir o SSE pelo Nginx em loopback na porta 3080. O guia abaixo registra
a composição original.

[compose.yml](compose.yml) sobe PostgreSQL 17 e backend, com volume persistente, healthchecks e API em loopback. Banco não publica portas. [Dockerfile](Dockerfile) usa Python 3.12, uv fixado e aplicação sem usuário root.

Na raiz: copie .env.example, defina senha e execute `uv run --locked python -m scripts.dev up`, depois `demo-compose`. `down` preserva volume. [Início rápido](../docs/00-comece-aqui/01-inicio-rapido.md).

Imagens têm tags; congelar digests e confirmar arquitetura/plataforma antes dos experimentos finais. Não há GPU, LLM ou acesso à VPS pressupostos.

[Operação](../docs/04-operacoes/operations.md) · [Backup](../docs/04-operacoes/backup-restore.md) · [Hostinger/rollback](../docs/04-operacoes/deploy-vps-hostinger.md) · [Guia da equipe](../docs/03-equipes/infra.md).

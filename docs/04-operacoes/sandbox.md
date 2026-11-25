# Sandbox de desenvolvimento (Dev Container)

Data: 22/11/2026. Ambiente isolado da `team/backend` para rodar backend, testes e portal sem depender da máquina local. A mesma configuração ([`.devcontainer/`](../../.devcontainer)) roda no **GitHub Codespaces** (nuvem) e no **Docker Desktop** (local, extensão Dev Containers do VS Code).

## O que vem nele

| Item | Versão | Origem |
| --- | --- | --- |
| Python | 3.12 (`python:3.12-bookworm`) | `.python-version`, `pyproject.toml` |
| uv | 0.11.13 | igual a `infra/Dockerfile` |
| Node | 22 | igual a `infra/portal.Dockerfile`; também em `.nvmrc` |
| PostgreSQL | 17 | igual a `infra/compose.yml` |

- Dependências instaladas pelos locks (`uv sync --locked`, `npm ci`), sem atualizar versões.
- `.venv` e `portal/node_modules` ficam em volumes do Docker, separados dos do host.
- O post-create roda Ruff, validação de links e a demo no PostgreSQL do sandbox.

## Isolamento

- Projeto Compose próprio (`ciia-backend-sandbox`), separado de `infra/compose.yml`.
- O PostgreSQL não publica porta no host; só o container `dev` o alcança. Ele não tem senha porque o banco é sintético e descartável. Não carregue nele documentos reais nem dados de produção.
- Bancos: `benchmark` (demo/chat, via `DATABASE_URL`) e `benchmark_test` (suíte, via `TEST_DATABASE_URL`).
- Backend e portal escutam em `127.0.0.1` dentro do container. O VS Code/Codespaces encaminha as portas 8000 e 3000; no Codespaces o encaminhamento é **privado** por padrão. Não torne as portas públicas: o portal ainda usa Next 14.2.35 com avisos críticos ([S1/S2](validacao-s1-s2.md)).
- Credenciais (tokens do chat, chave de LLM) não ficam no repositório. No Codespaces, use *Codespaces secrets* do usuário; localmente, `.env` (ignorado pelo Git).

## Uso

1. **Codespaces:** no GitHub, branch `team/backend` → *Code* → *Codespaces* → *Create codespace*. Exige permissão de Codespaces no repositório da organização.
   **Local:** Docker Desktop ligado → VS Code → *Dev Containers: Reopen in Container*.
2. Esperar o post-create terminar ("Sandbox pronto").
3. Comandos:
   - Suíte completa no PostgreSQL do sandbox: `uv run --locked python -m scripts.dev check`.
   - Backend: `uv run --locked python -m scripts.dev serve`.
   - Chat: seguir [chat.md](chat.md).
4. Recomeçar do zero: *Rebuild Container* ou apagar os volumes do projeto `ciia-backend-sandbox`.

## Limites

- O sandbox não corrige a versão do Next; só reduz a exposição.
- Não substitui a homologação H (infraestrutura real, backup e restauração) nem o deploy, que pertencem a Infra e à coordenação.
- No Codespaces, o custo e a cota são da conta/organização que cria o codespace.

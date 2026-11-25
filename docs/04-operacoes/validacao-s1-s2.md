# S1/S2 — dependências e segurança

Data: 22/11/2026. Worktree `team/backend`, HEAD `128f8af`, com alterações locais sem commit. Origem: achados 01, 02 e 09 da [auditoria de 28/10/2026](auditoria-backend-2026-10-28.md) e itens S1/S2 do [plano de melhorias](../02-arquitetura/backend-plano-lacunas.md#dependências-operação-e-consolidação). Decisão do responsável: S1 é corrigido no backend; S2 só é registrado, porque o portal também serve o site de documentação e a landing, mantidos por outra frente.

## S1 — dependências Python (corrigido)

`uv lock --upgrade-package certifi --upgrade-package opentelemetry-api`. O lock mudou só nesses dois pacotes:

| Pacote | Antes | Depois | Mínimo pedido pela auditoria | Quem depende |
| --- | --- | --- | --- | --- |
| certifi | 2026.7.22 | 2026.11.20 | 2026.10.19 (GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320) | httpx, httpcore |
| opentelemetry-api | 1.45.0 | 1.45.2 | 1.45.1 (GHSA-xcq7-p3pf-p88h) | fastapi |

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` | Instalou as duas versões novas |
| Versões importadas no ambiente | `certifi 2026.11.20`, `opentelemetry-api 1.45.2` |
| `ruff check .`, `ruff format --check .` | Sem erros |
| `scripts.validate_repository`, `scripts.export_openapi --check` | Sem erros; OpenAPI sem divergência |
| `pytest tests/backend/test_ready.py tests/backend/test_openapi.py tests/integration/test_roundtrip.py` | 5 aprovados |

A suíte completa com o lock novo roda na etapa seguinte, de isolamento dos testes e suíte PostgreSQL, para não executá-la duas vezes. As imagens de `infra/Dockerfile` precisam ser reconstruídas para receber o lock novo; isso fica com a homologação (H) e Infra.

## S2 — Next.js do portal (somente registro)

`npm audit --json` (só leitura) em `portal/`, 22/11/2026: **13 pacotes afetados** (1 crítico, 4 altos, 8 moderados). O `next` resolvido é **14.2.35**, a última versão da linha 14 (`next-14` no npm); não existe 14.x corrigida. O `next` sozinho soma 26 avisos: 3 críticos, 9 altos, 12 moderados e 2 baixos.

Críticos do `next`:

- [GHSA-p293-qw3h-jr36](https://github.com/advisories/GHSA-p293-qw3h-jr36): execução remota sem autenticação em servidor Windows (`>=13.4.0 <15.5.24`).
- [GHSA-2xp9-vwfh-vxw4](https://github.com/advisories/GHSA-2xp9-vwfh-vxw4): execução remota no otimizador de imagens com AVIF (`<15.5.24`).
- [GHSA-2464-fhr4-w9xw](https://github.com/advisories/GHSA-2464-fhr4-w9xw): execução remota no otimizador de imagens com SVG (`<=15.5.27`).

Outros pacotes: `postcss` (leitura de arquivo por `sourceMappingURL`), `glob`/`minimatch` e `@typescript-eslint/*` (cadeia do lint), `@tailwindcss/typography`/`postcss-selector-parser`.

**Exposição.**

- Chat do backend (`team/backend`): o processo do portal guarda o token do operador no servidor. O Compose publica só em `127.0.0.1:3000` e `127.0.0.1:3080`. Em desenvolvimento nesta máquina, o portal roda em **Windows**, que é a plataforma do primeiro aviso crítico.
- O código do portal não usa `next/image`, middleware nem Server Actions, e o `next.config.mjs` está vazio. O endpoint de otimização de imagens do `next start` continua existindo por padrão. A aplicabilidade real dos avisos de imagem não foi testada; nenhum exploit foi executado.
- **Na `main`:** [deploy-vps-hostinger.md](deploy-vps-hostinger.md) orienta publicar o portal na VPS por Nginx (`proxy_pass http://localhost:3000`), ou seja, exposto à rede com 14.2.35. O chat não está na `main`; o risco ali é do site de documentação.

**Alvo proposto para a frente do portal** (não aplicado):

- **15.5.29** (tag `backport` do npm). Pelos intervalos do `npm audit` de 22/11, é a primeira versão fora de todos os avisos do `next`, incluindo [GHSA-pc58-hwjq-p385](https://github.com/advisories/GHSA-pc58-hwjq-p385) (`<=15.5.28`).
- Alternativa: **16.4.6** (`latest`), que é a correção sugerida pelo `npm audit` e muda de versão principal.
- A linha 15 do App Router pede React 19; hoje o portal usa React 18.3 e `eslint-config-next` 14. A migração afeta as páginas de documentação, a landing e o chat. Por isso é um bloco isolado, sem `npm audit fix --force`, com lint, TypeScript, build e jornada completa depois.

**Encaminhamento.** Pendência para a frente do portal e a coordenação, antes de qualquer exposição compartilhada do portal (VPS incluída). Até lá, o chat do backend continua só em loopback.

## Risco registrado na `main` (não alterado)

`pipelines/RAG-main/RAG-main/app/data/raw/` e `processed/` contêm PDFs e JSON com nomes e conteúdo de processos SEI aparentemente reais (por exemplo, memorando da UNDF de 2024). O [AGENTS.md](../../AGENTS.md) proíbe documentos reais no repositório. Os arquivos pertencem a Documentos/RAG e não foram alterados nem copiados. Fica para a coordenação decidir sobre remoção e histórico. Esses arquivos não são usados nos testes do backend.

## Não verificado

- Suíte completa com o lock novo (etapa seguinte, isolamento e PostgreSQL).
- Reconstrução das imagens Docker.
- Aplicabilidade dos avisos do Next em execução real; build do portal em 15.5.29 ou 16.4.6.

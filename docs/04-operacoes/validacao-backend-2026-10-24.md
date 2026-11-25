# Validação local do backend — 24/10/2026

Entrega na worktree `backend-tools`, branch `team/backend`. A `origin/main`
consultada em `4987721` foi incorporada por merge local. O trabalho prévio de
`D:\benchmark-ciia-hermes` foi preservado e reaproveitado. Não houve push,
PR, implantação ou commit das alterações de implementação desta entrega.

## Escopo entregue

Seis tools com catálogo de schemas, regras independentes do transporte HTTP,
fronteira explícita com o corpus de Documentos/RAG, autenticação técnica,
gravações idempotentes e recibos verificáveis. API de conversas e execuções,
memória persistida, streaming com retomada, worker e protocolo de adaptadores.
Chat com marcador pseudônimo por navegador e consulta de artefatos; exportação
JSONL sem conteúdo textual por padrão; migração aditiva `0003`.

Referências: [PRD](../02-arquitetura/backend-prd.md),
[TDD](../02-arquitetura/backend-tdd.md), [ADRs](../05-decisoes/README.md),
[operação do chat](chat.md) e [integração de agentes](integracao-agentes.md).

## Evidências

| Verificação | Resultado |
| --- | --- |
| `uv sync --locked` | Instalação concluída, Python 3.12.10. |
| `uv run --locked python -m scripts.dev check` | Ruff, formato, links e invariantes aprovados; **42 testes aprovados em SQLite**. |
| Suíte completa com `TEST_DATABASE_URL` no PostgreSQL 17 isolado | **42 testes aprovados**. |
| `uv run --locked python -m scripts.dev demo` | Dados sintéticos; reingestão inseriu zero chunks. |
| `uv run --locked python -m scripts.tools_demo` em SQLite e PostgreSQL | Seis tools; duas gravações com replay idempotente e hashes conferidos por leitura independente. |
| `npm ci --no-audit --no-fund` no portal | Dependências instaladas. |
| `npm run lint`, `tsc --noEmit`, `npm run build` no portal | Aprovados; build de produção concluído após nova tentativa automática de download da fonte Inter. |
| Chat HTTP com backend e worker locais | Duas perguntas, quatro mensagens persistidas, memória confirmada; desconexão após primeiro delta e retomada com `Last-Event-ID` nas duas execuções. |
| Reinício e backup/restauração PostgreSQL 17 | `docker restart`, `pg_dump -Fc` e `pg_restore` em banco novo: contagens e hashes de conteúdo iguais nas **12 tabelas**. |

O relatório HTTP local fica em `data/http-chat-validation.json`, ignorado pelo
Git. São execuções do simulador sem LLM. Os testes dos adaptadores usam doubles
de protocolo; não certificam os produtos Hermes ou LangGraph.

O relatório de persistência fica em `data/postgres-validation-report.json` e o
dump em `data/backend-validation-restore_*.dump`, ambos fora do Git. O teste
operacional usou comandos nativos contra container isolado, sem validar o wrapper
Compose de backup. Após o reinício, a porta dinâmica publicada pelo Docker mudou;
a verificação consultou novamente essa porta antes de comparar os conteúdos.

Avisos mantidos: depreciação Starlette/HTTPX nos testes e regra de imagem em
`portal/app/team/page.tsx`, preexistente. A ferramenta de navegador expirou nas
duas tentativas desta rodada; inspeção visual e interação manual no portal não
foram confirmadas nesta data. Build e verificações HTTP não substituem essa etapa.

## Limites e próxima integração

Runtimes reais, URL/versão do Hermes, modelo/endpoint e adaptadores homologados
dependem das equipes responsáveis. Busca atual é literal no corpus de teste;
recuperação semântica e ingestão são responsabilidade de Documentos/RAG.
O marcador de participante organiza conversas, mas não autentica pessoas.
Imagens completas da aplicação, proxy Nginx nesta rodada e implantação em VPS
não foram validados. A coleta comparativa real ainda não foi executada.

Mudanças de contratos e consumidores estão documentadas e testadas localmente;
a revisão das equipes afetadas permanece necessária antes da integração remota.

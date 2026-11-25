# Correções de streaming e polling — 25/10/2026

Trabalho local na worktree `backend-tools`, branch `team/backend`, em atendimento
aos dois apontamentos enviados pelo responsável. Alterações da implementação
anterior preservadas; sem commit, push ou PR.

## Comportamento corrigido

- Ao selecionar novamente uma conversa durante a resposta, o chat fecha a
  conexão anterior e incrementa a geração do acompanhamento após carregar o
  snapshot. O efeito reabre o EventSource pelo cursor recebido mesmo quando
  os IDs da conversa e do run continuam iguais. Se o carregamento falhar,
  reabre o acompanhamento pelo snapshot anterior e apresenta o erro.
- O worker contínuo trata HTTP 503 no claim aguardando dois segundos antes
  de continuar o polling. Cada polling permanece uma nova reserva. O modo
  `--once` e erros definitivos, como 401/403, continuam encerrando com erro.
  Os logs registram somente `status=backend_unavailable`.

API, schemas, dependências e banco permanecem compatíveis. A mudança de polling
resolve o achado A04 da [auditoria anterior](auditoria-backend-2026-10-24.md).
A correção de seleção na interface é distinta das corridas de leitura do backend
A01/A02; o relatório histórico não foi reescrito para declarar esses itens resolvidos.

## Evidências desta rodada

- Antes da correção, os dois casos de recuperação do worker falharam porque
  a primeira resposta 503 encerrava o processo; três casos de erro definitivo
  e `--once` já passavam.
- Após a correção, `uv run --locked python -m pytest tests/backend/test_worker_polling.py`:
  **5 testes aprovados**. MockTransport cobre um e três 503 seguidos de reserva
  válida, 401/403 e `--once`; a espera é substituída nos testes.
- `uv run --locked python -m scripts.dev check`: lint, formato, links e invariantes
  aprovados; **47 testes aprovados em SQLite**, incluindo backend e integração.
- `uv run --locked python -m scripts.dev demo`: consulta aprovada e reingestão
  com zero chunks novos.
- Portal: `npm run lint` e TypeScript (`tsc --noEmit`) aprovados.
- `npm run build`: build de produção Next.js 14.2.35 concluído com sucesso.
- Chromium headless sobre o build de produção, com API e EventSource simulados:
  cliques repetidos na conversa ativa reabrem pelo cursor correto, mantêm uma
  única conexão ativa, recebem deltas e `done` e desbloqueiam **Enviar**.
  Falha no carregamento do snapshot apresenta erro e retoma o acompanhamento
  anterior. Trocar de conversa fecha a conexão e retornar reabre uma única vez.
  Os três cenários passaram; o primeiro ensaio parou por ambiguidade no seletor
  de alerta do teste, corrigida antes da execução final.

A verificação de navegador está em `data/verify_stream_reselection.cjs`, ignorada
pelo Git, com captura `data/stream-reselection-validation.png`. Foi executada
com Node e uma instalação de Playwright já disponível no cache local, sem
adicionar dependências ao projeto. Para repetir, inicie o portal na porta 3017
e execute `node data/verify_stream_reselection.cjs CAMINHO_DO_MODULO_PLAYWRIGHT`.
É prova do ciclo da interface em navegador real com eventos controlados; não
substitui uma rodada com SSE/worker e agentes reais.

Avisos preservados: depreciação Starlette/HTTPX e regra de imagem preexistente em
`portal/app/team/page.tsx:150`. PostgreSQL, restart/restauração, agentes reais e
implantação não são revalidados por esta rodada, que não altera SQL ou schema.

O servidor temporário de verificação foi encerrado ao final. O relatório de
auditoria anterior permanece como registro histórico dos achados originais.

# A9 — SSE com admissão durável por operador

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A9 do plano](../02-arquitetura/backend-plano-blocos.md). Sem publicação.

## Implementação e workflow

GET /runs/{id}/events autentica, valida cursor e propriedade/grants antes de abrir o fluxo.
open_stream relê e trava o perfil do operador, confirma credencial atual e autorização do run e remove seus leases expirados.
Conta os leases restantes de todos os runs desse operador e admite no máximo cinco. O controle reside em stream_leases, não na memória de um processo.
Sem capacidade, retorna 429 resource_limit, retryable true, no-store, antes dos cabeçalhos SSE. Não consome cursor nem cria sexto lease.
A migração aditiva 0008 cria a tabela com lease_id, principal_id, run_id e lease_until e índice por operador.
Não há backfill de sessões ou mudança de eventos/runs. Downgrade remove somente a tabela nova, em banco sintético no teste.
Aplicações devem migrar o banco antes de usar o endpoint; não houve migração de banco operacional.

Lease SSE dura 30 segundos. O laço mantém autenticação e grants por polling e confere que seu lease permanece válido.
Renova quando restam no máximo 15 segundos. Reserva expirada/removida não ressuscita; produz stream_error conflict e encerra.
Nova conexão recupera leases abandonados no próprio banco. Um processo congelado perde admissão após o prazo e deve encerrar quando retomar.
O limite é de admissões duráveis válidas; não há promessa de encerrar à distância um socket de processo congelado ou rede particionada.
Relógios entre hosts precisam ser coerentes, como nos demais leases; essa operação distribuída não foi homologada aqui.

LeasedStreamingResponse libera a reserva em finally ao completar, falhar ou desconectar, mesmo quando o corpo não chegou a ser iterado.
A limpeza é protegida do cancelamento de tarefas do Starlette. Falha SQL na liberação gera aviso seguro; o TTL permite recuperação posterior.
Não há garantia de liberação imediata se o banco estiver indisponível ou o processo morrer.
Os handlers não mantêm conexão de banco ocupada durante a espera SSE.

## Contrato, consumidores e respostas

Eventos, IDs, ordenação, Last-Event-ID, after e reconexão mantêm os contratos anteriores.
401/403/404/422/503 antes de abrir continuam em envelope HTTP. Excesso acrescenta 429, sem Retry-After estimado ou retry automático.
Após abrir, falhas continuam como um stream_error seguro; revogação de grants interrompe o fluxo.
Terminal emite done persistido e encerra; a limpeza não cria evento novo nem altera cursor.
Não há token de lease SSE público nem novo cabeçalho exigido dos clientes. Portal e consumidores devem tratar 429 e repetir a partir do último cursor após liberação de capacidade.
OpenAPI e referência da API documentam cinco conexões e TTL de 30 segundos.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/backend/test_a9.py tests/backend/test_a0.py::test_sse_before_and_after_headers tests/backend/test_a0.py::test_sse_domain_failure_after_open_and_missing_run_before_open tests/backend/test_execution.py::test_event_replay_sse_cursor_and_result_consistency tests/backend/test_openapi.py --durations=5
```

**14 aprovados em SQLite em 133,11 segundos**, log tmp/a9-directed.log.
Oito próprios cobrem cinco admissões/recusa HTTP antes da abertura, cursor inválido sem novo lease, recuperação exata do prazo,
renovação e recusa de ressurreição, disputa real de dois subprocessos pela última vaga,
três jornadas HTTP de término/cancelamento/revogação, falha de envio de cabeçalhos antes do corpo e downgrade/upgrade sem perder run.
Os subprocessos usam o mesmo SQLite e identidades exclusivamente sintéticas. Provaram uma admissão e um 429, sem sexto lease.
Seis regressões próximas cobrem erros SSE antes/depois dos cabeçalhos, erro de domínio, cursor/deltas/resultado e OpenAPI.
Nenhuma asserção funcional falhou na seleção. Lint detectou uma expectativa genérica de exceção no teste de socket;
ela foi especificada como ClientDisconnect conforme o código da versão instalada do Starlette. Aviso Starlette/HTTPX existente permanece.

Lint/formato, exportação OpenAPI, links/invariantes e whitespace conferidos.
Aceite A9 comprovado localmente, inclusive admissão em processos separados sobre SQLite; isso não homologa PostgreSQL.
Suíte completa reservada ao fechamento A. PostgreSQL, relógios entre hosts, rede/proxy reais, LLMs reais e revisão manual CTO/Astra pendentes.
Sem commit, push, PR, deploy ou revisão automática.

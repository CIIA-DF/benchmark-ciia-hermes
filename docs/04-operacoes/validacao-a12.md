# A12 — Listagem autorizada de processos

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A12 do plano](../02-arquitetura/backend-plano-blocos.md).

## Achado, correção e workflow

Uma linha autorizada podia conter JSON estruturalmente válido com process_id de outro processo; GET /processos devolvia esse payload com 200.
A sonda dirigida reproduziu a falha em 3,77 segundos antes da correção; log tmp/a12-before.log.

A consulta continua filtrando permissões no SQL e ordenando por processo/corpus. Agora seleciona também a identidade da linha.
Cada payload passa por Process e precisa corresponder ao process_id/corpus_version selecionados.
Inconsistência acessível retorna 500 invalid_response seguro, sem lista parcial nem conteúdo interno.
Linha corrupta fora do escopo autorizado não é lida nem exposta. Falta de concessões mantém 200 com lista vazia.
Não houve paginação, ingestão, alteração de corpus, migração ou novo campo público.

401/403 preservam autenticação e papel; 503 mantém falha de banco. Respostas privadas mantêm no-store.
App/OpenAPI documentam 500 e a identidade validada; consumidores seguem list[Process] e o envelope de erro anterior.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/backend/test_a12.py tests/backend/test_a0.py::test_auth_domain_input_output_and_internal_errors_are_distinct tests/backend/test_openapi.py --durations=5
```

**9 aprovados em SQLite em 26,76 segundos**, log tmp/a12-directed.log.
Seis próprios verificam identidade estrangeira de processo/corpus, versão ausente, tipo inválido, JSON null,
saída tipada, corrupção sem concessão, revogação, vazio válido e autenticação/papel.
Três regressões próximas verificam envelopes e OpenAPI. Aviso Starlette/HTTPX existente permanece.
A reprodução anterior não conta como outro teste aprovado.
Lint/formato, OpenAPI, links/invariantes e whitespace conferidos.

Aceite A12 comprovado localmente. Suíte completa reservada ao fechamento A.
PostgreSQL, worker/LLM reais e revisão manual CTO/Astra pendentes.
Sem commit, push, PR, deploy ou revisão automática.

## Fechamento posterior do bloco A

Após o aceite A13, suíte completa aprovada: 390 testes SQLite em 1.328,12 s. Os nove testes dirigidos acima fazem parte desse conjunto.
[Relatório consolidado A](validacao-a-fechamento.md).

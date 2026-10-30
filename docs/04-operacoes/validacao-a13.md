# A13 — Fronteira HTTP das seis ferramentas

Data: 30/10/2026. Worktree oficial C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: [A13 do plano](../02-arquitetura/backend-plano-blocos.md). Sem revisão automática ou publicação.

## Achados reproduzidos

A 1.001ª requisição atribuível ao run ainda retornava 200. Sonda antes da correção: falha esperada em 9,56 s; tmp/a13-before.log.
Após trocar o executor do worker no perfil, consultar_processo ainda retornava 200 com a lease antiga.
Sonda antes da correção: falha esperada em 3,64 s; tmp/a13-executor-before.log.

## Implementação comum e workflow

A entrada HTTP das seis rotas continua criando um UUID físico antes da validação.
Agora autentica a credencial, identifica o titular pela lease e trava o run para atribuir a tentativa e contar os UUIDs físicos persistidos.
A decisão é confirmada antes de ler/validar o corpo ou executar o efeito. ID de run fornecido no corpo não atribui tentativas a terceiros.
Uma credencial inválida, perfil operador ou lease desconhecida mantém tentativa não atribuída; os handlers anteriores decidem sua recusa.
Lease reconhecida do titular permite auditar também erro de corpo, método, tamanho, contexto ou estado expirado, sem autorizar efeito.

MAX_PHYSICAL_ATTEMPTS_PER_RUN vale 1.000, agregado entre as seis tools do mesmo run. A milésima é admitida;
a seguinte retorna 429 resource_limit, retryable false e no-store, antes da execução. Retry com mesmo ID lógico também é nova tentativa física.
A resposta recusada é registrada com o UUID físico original, fase failed e código/status; client_received continua null.
X-Tool-Call-Id válido é preservado quando fornecido. Corpo não lido mantém args_sha256 desconhecido; não há hash inventado.
Sem cabeçalho lógico válido, a recusa anterior à validação não inventa uma reserva lógica.

O teto limita admissão para execução, não apaga recebimentos: 1.000 tentativas anteriores e duas recusas produzem 1.002 registros físicos.
Recusas posteriores também permanecem auditadas. Não há alegação de máximo de 1.000 linhas de auditoria, nem limite global de requisições sem autenticação.
Registros físicos existentes entram na contagem; ledger legado anterior ao F0 não é convertido em tentativas fictícias.
Contador usa a identidade física, não fases ou reservas lógicas. Outro run conserva quota independente.
Sem nova migração/configuração, exclusão de histórico, mudança na regra de orçamento lógico ou reescrita das regras F.

worker_run também recusa executor autenticado incompatível com o run, antes da leitura/efeito, para todas as tools e demais operações de worker.
Autenticação atual, grants, permissões de escrita e rechecagem T0-R1 permanecem. Não se trata o ID lógico como autenticação ou prova de recebimento.
Limite físico não encerra o run: envio do resultado continua disponível; não é o limite de eventos terminal do A8.
Falha SQL na admissão retorna 503 seguro, sem executar a tool. Falha ao persistir resposta conserva a incerteza de transporte F0.

## Catálogo individual e contratos

| Rota | Verificação própria após A0 | Regra de negócio preservada |
| --- | --- | --- |
| consultar_processo | Autenticação, lease, executor, ID, corpo, resposta ProcessResult e replay | Metadados/inventário F1 |
| buscar_documentos | Mesma fronteira, SearchResult tipado e replay | Busca literal/escopo F2 |
| ler_documento | Mesma fronteira, DocumentResult tipado e replay | Identidade/páginas/hash F3 |
| consultar_requisitos | Mesma fronteira, RequirementsResult tipado e replay | Checklist versionado F4 |
| registrar_pendencia | Mesma fronteira, WriteReceipt, replay e mesmo artefato | Integridade/evidências/permissões F5 |
| salvar_minuta | Mesma fronteira, WriteReceipt, replay e mesmo artefato | Persistência/idempotência F6 |

Cada rota mantém 200 válido, 401 com challenge Bearer, 403 de papel/lease/executor, 422 de corpo/ID, 413 acima de 1 MiB e no-store.
Novidade comum: quota física 429 não repetível no mesmo run. OpenAPI acrescenta sua descrição a cada operação e mantém os schemas/cabeçalhos.
Erros de negócio, conflito lógico e versão permanecem nos contratos anteriores; regressões T0-R1/R2 conferem revogação e reserva durável.
Consumidores devem diferenciar quota de fila/SSE retryable true da quota física retryable false; não repetir automaticamente 429 permanente.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/backend/test_a13.py tests/backend/test_t0_r1.py tests/backend/test_t0_r2.py tests/backend/test_f0.py::test_unauthenticated_request_is_not_attributed_to_untrusted_run tests/backend/test_openapi.py --durations=5
```

**32 aprovados em SQLite em 62,67 segundos**, log tmp/a13-directed.log.
Dezesseis próprios: seis matrizes HTTP individuais, seis recusas de executor incompatível, fronteira real 999/1.000/1.001,
erros de JSON/método/tamanho consumindo admissão, disputa pela última vaga com uma única minuta e isolamento entre runs.
Dezesseis regressões próximas conferem reservas/erros/revogação T0, atribuição F0 e OpenAPI.
Sondas anteriores e repetições não entram no total distinto. Aviso Starlette/HTTPX existente permanece.

Lint/formato, OpenAPI, links/invariantes e whitespace conferidos. Aceite A13 comprovado localmente.
Suíte completa fica no fechamento A, após este aceite. PostgreSQL, processos separados para esta quota, LLMs reais e revisão manual CTO/Astra pendentes.
Concorrência da quota foi verificada em threads sobre SQLite; não homologa isolamento PostgreSQL.
Sem commit, push, PR ou deploy.

## Fechamento posterior do bloco A

Após este aceite dirigido, scripts.dev check passou: 390 testes SQLite em 1.328,12 s; comando completo em 1.336,15 s.
Lint global, formato de 212 arquivos e links/invariantes também aprovados. Os 32 testes dirigidos acima fazem parte da suíte completa.
[Relatório consolidado A](validacao-a-fechamento.md), com campos/códigos, workflow, limites e pendências para revisão manual.

# A3 — Quota da fila em POST /runs

Data: 30/10/2026. Escopo: A3 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree oficial `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend` conferida.
Testes dirigidos; suíte completa reservada ao fechamento A, conforme pedido. Relatório conciso.

## Falha reproduzida

POST /runs aceitava uma 21ª execução queued do mesmo operador, com 202.

```sh
uv run --locked python -m pytest tests/backend/test_a3.py::test_twentieth_is_allowed_replay_precedes_quota_and_claim_frees_slot --durations=5
```

Antes da correção: uma falha esperada, 1,96 s. O teste esperava 429 e recebeu 202.
Dados e banco exclusivamente sintéticos.

## Implementação e configuração

[ExecutionService.ensure_queue_capacity](../../services/backend/execution.py) conta linhas runs com owner_id do operador e status queued.
Padrão: 20. [Configuração de exemplo](../../.env.example): RUN_MAX_QUEUED_PER_OPERATOR=20.
O valor precisa ser inteiro positivo; zero, negativo ou texto inválido impedem inicialização. As instâncias da API devem usar a mesma configuração operacional.

O contador inclui todos os runs queued do operador, independentemente de processo, corpus, executor ou kind.
Running, succeeded, failed e timed_out não consomem a quota de fila. Outro operador tem contagem própria.
Capacidade deriva das linhas persistidas; não há contador em memória, reserva separada de vaga ou migração nova.

A3 aplica a verificação à criação nova de benchmark por POST /runs.
Mensagens de conversa já enfileiradas entram na contagem, mas a aplicação da quota no produtor de mensagens pertence a A4.
Logo, este sub-bloco não fecha a proteção de todos os produtores de fila do backend.

## Workflow e atomicidade

1. Framework valida RunInput e autentica operador.
2. Serviço preserva a expiração já existente de running; expiração específica de queued continua no A5.
3. Transação adquire a trava do principal, já usada para serializar criação/reenvio.
4. Busca chave idempotente do proprietário. Revalida concessão e devolve o run existente antes da quota se a entrada coincide.
5. Mesma chave com entrada diferente continua 409 idempotency_conflict, inclusive com fila cheia.
6. Para entrada nova, valida executor, concessões, processo/versões e limite textual.
7. Sob a mesma trava, conta queued e verifica capacidade antes da geração/inserção do novo run.
8. Com vaga, grava run e evento inicial na mesma transação e retorna 202 RunResponse.
9. Sem vaga, retorna 429 resource_limit; não grava run, mensagem ou evento. A chave recusada pode ser usada quando surgir capacidade.
10. Claim muda queued para running e libera vaga pela própria mudança de estado; não reabre nem duplica runs.

SQLite usa BEGIN IMMEDIATE na transação existente. PostgreSQL usa o SELECT FOR UPDATE do principal antes de contar/inserir; a homologação nesse banco permanece pendente.
A regra não depende de memória compartilhada entre aplicações. Rollback da inserção/evento preserva a capacidade disponível.
Não se alteraram claim, leases, encerramento, memória ou integridade das ferramentas.

## Contrato e respostas

[ErrorCode](../../contracts/models.py) acrescenta resource_limit. RunInput, RunResponse e campos de ToolError permanecem iguais.
[ToolFailure/fail](../../services/backend/errors.py) recebem retryable opcional, keyword-only, com padrão false preservado para os chamadores anteriores.
O novo ponto de recusa de quota usa retryable true; chamadores anteriores mantêm seus valores.

| Situação | HTTP | code / resposta |
| --- | --- | --- |
| Criação com vaga | 202 | RunResponse queued |
| Replay idêntico, mesmo com fila cheia | 202 | Mesmo run_id; não ocupa outra vaga |
| Mesma chave, outra entrada | 409 | idempotency_conflict |
| Fila do operador no limite ou acima | 429 | resource_limit, retryable true |
| Credencial inválida / perfil ou concessão recusados | 401 / 403 | unauthorized / forbidden |
| Versão incompatível | 409 | version_mismatch |
| Executor desabilitado | 503 | executor_unavailable |
| Falha SQL | 503 | storage_unavailable |

429 usa envelope tipado e Cache-Control no-store, sem eco do conteúdo.
Não envia Retry-After: não há previsão confiável de quando um worker liberará capacidade. retryable indica possibilidade futura, não espera garantida ou retry infinito.
O servidor não agenda reenvio. O consumidor deve preservar a mesma chave/entrada ao tentar novamente, evitando duplicação após perda de resposta.
Validações anteriores à quota conservam prioridade; a quota não substitui autorização nem validação de processo/executor.

[app.py](../../services/backend/app.py) e [OpenAPI](../../services/backend/openapi.yaml) publicam 429 e a política do endpoint.
Consumidores que validam enum/código/status precisam incorporar resource_limit/429 e tratar capacidade temporária.
Backend, adaptadores e consumidores de criação de runs devem revisar antes de integrar. Os demais blocos de limites continuam separados.

## Testes próprios

Novo [test_a3.py](../../tests/backend/test_a3.py): sete casos pytest.

- Vinte criações HTTP aceitas; 21ª recusada; ausência de efeitos na recusa; replay e conflito preservados com fila cheia; claim libera vaga para a mesma entrada recusada.
- Duas aplicações com engines independentes sobre o mesmo banco, disputando uma única vaga: um 202 e um 429; replay concorrente da entrada vencedora não duplica run/evento.
- Contagem por operador, incluindo chat queued e excluindo outros estados; operador independente continua criando.
- Autenticação, escopo, versão, executor e grant revogado preservados, inclusive na fila cheia.
- Falha na gravação do evento inicial faz rollback do run e da capacidade; a mesma chave pode ser repetida com sucesso.
- Valor padrão 20, configuração positiva alternativa e configurações inválidas.
- Outro processo concedido ao mesmo operador não fornece quota independente.

Nos cenários de contagem, estados não queued são preparados diretamente apenas no banco temporário; não se afirma homologação das transições por essa preparação.
Concorrência usa threads e duas instâncias de aplicação/engine, não processos separados nem PostgreSQL.
Contagens de runs, queued, eventos e mensagens são conferidas diretamente no banco.

Cinco regressões próximas: replay de mensagem/conversa ativa, claim específico, claim concorrente e dois testes OpenAPI.

```sh
uv run --locked python -m pytest tests/backend/test_a3.py tests/backend/test_execution.py::test_message_replay_conflict_and_single_active_run tests/backend/test_execution.py::test_targeted_claim_does_not_take_another_queued_run tests/backend/test_execution.py::test_duplicate_and_concurrent_claim tests/backend/test_openapi.py --durations=10
```

**12 aprovados em SQLite, 31,17 s**, em uma seleção dirigida: sete próprios e cinco próximos.
A reprodução anterior não é teste adicional aprovado. Log: tmp/a3-directed.log; código final 0 em tmp/a3-directed.exit.

Maiores preparações: 6,11 s no caso de outro processo, 5,27 s em rollback, 4,71 s em configuração e 4,62 s no limite padrão.
Maior chamada registrada: 1,95 s no caso de outro processo. Medição local não isola causa nem comprova desempenho em PostgreSQL/produção.
Um aviso existente de depreciação Starlette/HTTPX permanece.

## Verificação e pendências

Lint e formato dos cinco arquivos Python alterados aprovados. Uma descrição inicial excedia o limite de linha e foi corrigida antes da seleção dirigida.
Diff da implementação foi comparado à cópia anterior ao A3; alterações anteriores preservadas. OpenAPI regenerado.
`uv run --locked python -m scripts.export_openapi --check`: aprovado.
`uv run --locked python -m scripts.validate_repository`: aprovado.
`git -c core.safecrlf=false diff --check`: aprovado.
Estado: A3 implementado e verificado localmente com 12 testes dirigidos em SQLite, disponível para revisão manual.

Suíte completa não executada, conforme solicitação: fica para o fechamento do bloco A.
PostgreSQL, processos separados, runtimes reais e revisão CTO/Astra continuam pendentes. Testes desta entrega usam SQLite temporário em C:.
A4 aplicará quota ao produtor de mensagens e verificará sua atomicidade; A5 tratará expiração queued. Não afirmar proteção global da fila antes desses blocos.
Sem merge de main nesta worktree com alterações locais e autorização restrita à entrega local.
Sem commit, push, PR, publicação, deploy ou revisão automática. A4 não iniciado.

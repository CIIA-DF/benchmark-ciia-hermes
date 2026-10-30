# A2 — Reconciliação do resultado experimental

Data: 30/10/2026. Escopo: A2 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree oficial `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend` conferida.
Testes dirigidos conforme solicitação do responsável; suíte completa reservada ao fechamento A. Relatório conciso.

## Achado e implementação

A finalização conferia contexto/metadados do experimento e existência de artefatos no run, mas aceitava chamada inventada.
A sonda never-executed, sem qualquer chamada observada, retornou 200 e encerrou o run.

Reprodução anterior à correção:

```sh
uv run --locked python -m pytest tests/backend/test_a2.py::test_never_executed_is_rejected --durations=5
```

Uma falha esperada na comparação 422/200, em 9,01 s. Dados exclusivamente sintéticos.

Novo [result_integrity.py](../../services/backend/result_integrity.py) recebe Connection, run persistido e ExperimentRun tipado; valida sem gravar nenhuma dessas fontes.
[ExecutionService.finish](../../services/backend/execution.py) chama o validador dentro da transação que já mantém a trava do run, antes da atualização terminal.
Respostas, modelos públicos, algoritmos de hash, escritores e migrações permanecem iguais.
[app.py](../../services/backend/app.py) e [OpenAPI](../../services/backend/openapi.yaml) descrevem as novas exigências sem acrescentar campo ou código de erro.

## Correspondência aplicada

| Dado | Regra |
| --- | --- |
| IDs lógicos declarados | Únicos; conjunto igual à união de reservas, tentativas físicas atribuídas e ledger legado do run |
| Ferramenta | Coincide com a reserva durável; sem reserva, exige identidade de ferramenta inequívoca no histórico atribuível |
| Argumentos | Hash da reserva seleciona as observações compatíveis; não confunde tentativa recusada por reutilização com a operação original |
| status ok | Exige 200 físico observado ou resposta desconhecida com operação concluída; no legado, conclusão observada sem inferir número/resposta física |
| Escrita ok | Exige artifact_id confirmado para aquela chamada |
| Artifact_id | Permitido somente nas escritas; pertence ao run, à ferramenta e ao efeito da chamada; entrada confere hash reservado quando disponível |
| Artefato referenciado | Reutiliza validate_artifact de F5/A1 para contexto, payload canônico, chave, hashes, UUID e recibo |
| persisted_artifact_ids | Sem duplicações; igual aos IDs não nulos declarados nas chamadas |
| Durações | Tipagem e limites existentes preservados; nenhuma igualdade entre duração do cliente e servidor |

Também entram chamadas atribuídas que falharam antes da reserva lógica, como quota de orçamento excedida.
IDs de outros runs não são aceitos. Um registro de erro não permite inventar uma identidade inexistente no servidor.

## Transporte, efeitos e limites da evidência

Cliente e servidor continuam fontes separadas. O registro enviado não é convertido em prova de entrega nem sobrescrito pelo histórico.

- Cliente pode declarar error mesmo com 200 preparado pelo servidor, porque a resposta pode ter sido perdida ou recusada pelo consumidor.
- Cliente pode declarar error sem artifact_id mesmo quando existe efeito confirmado. Esse efeito continua visível no snapshot/histórico do servidor.
- persisted_artifact_ids não precisa listar todos os efeitos observados; precisa corresponder aos IDs que o próprio cliente declara nas chamadas.
- Efeito confirmado com resposta conhecida somente como 503 não basta para declarar ok. Retry posterior com 200 e recibo íntegro torna o relato ok compatível.
- Se a coleta do HTTP falhar, status null permanece desconhecido. Uma operação concluída pode ser compatível com o relato ok; uma reserva sem conclusão não o sustenta.
- client_received permanece null. Aceitar o relato não certifica recebimento, compreensão, qualidade semântica ou sucesso científico.
- Falha de conexão anterior a qualquer identidade atribuída não vira execução observada. O fluxo failed sem experiment continua aceito, como no tratamento de adapter_error do worker.

Ledger legado pode sustentar identidade/conclusão e vínculo do efeito, mas não é contado como tentativas físicas.
Não houve backfill, reconstrução de respostas recebidas ou alteração de observações antigas.

## Workflow

1. Worker recebe contexto e lease pelo claim.
2. Clientes comuns geram tool_call_id por chamada lógica e conservam ID/corpo no retry.
3. Tools registram reserva, tentativas físicas, fases e artefatos; cada fonte mantém seu significado.
4. Adaptador envia AgentResult com ExperimentRun quando aplicável.
5. Finalização valida worker/lease, fontes, deltas, contexto/metadados e campos de avaliação independente.
6. A2 confronta chamadas/artefatos sob a trava do run. Divergência retorna erro sem encerrar nem criar done.
7. Resultado aceito é persistido tal como declarado, junto ao desfecho terminal. Histórico observado permanece separado.
8. Repetição idêntica continua 200; outro conteúdo retorna 409. Observações posteriores não invalidam o replay de resultado já aceito.

O ramo idempotente terminal conserva a regra anterior: não revalida resultados históricos nem reescreve o resultado após novas observações.
Chat sem registro experimental e falhas sem experiment preservam o comportamento anterior. Benchmark sucedido continua exigindo experiment.
verified_success e evaluator continuam exclusivos da avaliação independente e devem ser null no envio do agente.

| Situação | HTTP | code |
| --- | --- | --- |
| Registro compatível / replay idêntico | 200 | RunResponse |
| IDs inventados, ausentes ou repetidos; ferramenta/status incompatível | 422 | validation_error |
| Artefato estrangeiro, trocado, omitido ou sem vínculo declarado | 422 | validation_error |
| Resposta final divergente dos deltas | 422 | validation_error |
| Artefato/contexto persistido inconsistente | 500 | invalid_response |
| Resultado terminal diferente | 409 | idempotency_conflict |
| Worker/lease incompatível | 403 | forbidden |
| Credencial inválida | 401 | unauthorized |
| Falha SQL | 503 | storage_unavailable |

A0 continua responsável pelo envelope seguro, no-store e challenge. Não se ecoam IDs, conteúdo ou SQL rejeitados nas mensagens.

## Testes próprios e regressões próximas

Novo [test_a2.py](../../tests/backend/test_a2.py): 13 casos pytest próprios.
Cobrem never-executed como ok/error, conjuntos fechados, duplicações, ferramenta divergente, falso sucesso, leitura com artefato e durações diferentes preservadas.
As duas escritas cobrem vínculo por chamada, troca de artefatos dentro do mesmo run, IDs desconhecidos, omissões e duplicação de listas.
Também cobrem artefato real de outro run, recibo persistido corrompido, ausência de done/encerramento em rejeições, deltas, replay idêntico/diferente e chamadas tardias.

Transporte: pós-commit com/sem retry, coleta incompleta do HTTP com/sem conclusão, três respostas 200 perdidas por cliente real ToolClient com MockTransport e um único efeito.
Demais casos: orçamento recusado sem reserva, identidade legada sem inventar precisão física e falha de adaptador sem experiment.
A simulação do legado remove apenas linhas do banco temporário do teste; não migra banco operacional.

Seis regressões próximas: benchmark simulado declarando as quatro chamadas reais, SSE/deltas, lease/evidência cruzados, worker de chat e dois testes OpenAPI.

```sh
uv run --locked python -m pytest tests/backend/test_a2.py tests/backend/test_tool_calls.py::test_simulation_declares_the_calls_recorded_by_the_server tests/backend/test_execution.py::test_event_replay_sse_cursor_and_result_consistency tests/backend/test_execution.py::test_cross_run_lease_and_evidence_are_rejected tests/backend/test_execution.py::test_simulation_worker_end_to_end tests/backend/test_openapi.py --durations=10
```

Primeira seleção: **17 aprovados e duas sondas falharam**, 56,49 s. A injeção dessas sondas atingia a validação anterior ao commit e, corretamente, não deixava artefato.
A sonda foi corrigida para atingir a releitura independente após commit, como na prova F0. Confirma diretamente artefato persistido e fase effect_confirmed.
Nenhum código de produção mudou entre essa seleção e a repetição das duas sondas.

```sh
uv run --locked python -m pytest tests/backend/test_a2.py::test_post_commit_failure_preserves_observed_effect_and_client_outcome --durations=5
```

Repetição corrigida: **2 aprovados, 12,31 s**. Resultado: **19 casos distintos verificados**, 13 próprios e seis próximos, em duas execuções dirigidas.
Os 68,80 s são a soma dessas duas execuções; não representam uma rodada única de 19 aprovações. A reprodução inicial é separada.
Logs: tmp/a2-directed.log e tmp/a2-postcommit.log. O primeiro conserva as duas falhas da sonda; o segundo registra código final 0 em tmp/a2-postcommit.exit.
Não somar repetições como testes distintos.

Maior preparação da seleção: 27,07 s no caso de integridade/artefato estrangeiro; chamada 9,36 s nesse caso e 8,80 s na perda de respostas.
Na repetição, preparação máxima 4,73 s e chamada máxima 3,87 s. A amostra não isola causa nem mede desempenho real de agentes.
Um aviso existente de depreciação Starlette/HTTPX permanece.

## Verificações, consumidores e pendências

Lint/formato dos quatro arquivos Python alterados aprovados; diff de execução, app e schema comparado à cópia anterior ao A2.
Contratos públicos preservados; validação semântica ficou mais estrita. Adaptadores devem declarar todas as chamadas atribuídas, incluindo erros, e listas de artefatos coerentes.
Clientes comuns síncrono/assíncrono foram exercitados por transporte controlado e simulador, sem alteração de seu código.
Backend, Hermes/LangGraph, consumidores experimentais e Metodologia devem revisar o novo aceite antes de integrar.

`uv run --locked python -m scripts.export_openapi --check`: aprovado.
`uv run --locked python -m scripts.validate_repository`: aprovado.
`git -c core.safecrlf=false diff --check`: aprovado.
Estado: A2 implementado e verificado localmente por 19 casos distintos em SQLite, disponível para revisão manual.
Suíte completa não executada por solicitação explícita: fica para o fechamento do bloco A.
PostgreSQL, adaptadores/LLMs reais e revisão CTO/Astra continuam pendentes; esta etapa só comprova SQLite/protocolo sintético.
Sem merge de main com alterações locais e autorização restrita ao trabalho local. Sem commit, push, PR, publicação, deploy ou revisão automática.
A3 não iniciado. Não é aceite global de segurança ou de resultados científicos.

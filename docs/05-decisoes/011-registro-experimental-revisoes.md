# ADR 011 — registro experimental com revisões (port do LangGraph)

Data: 21/11/2026. Estado: implementado localmente na `team/backend`, sem commit; revisão do LangGraph (João Enomoto) e da Metodologia pendente.

## Contexto

Em 18/11/2026, João Enomoto criou no `task/langgraph-grafo` (commit `856ff06`) um registro de `ExperimentRun` para o adaptador LangGraph gravar e reler a medição de cada execução:

- rotas `POST /experiments`, `GET /experiments/{run_id}`, `PUT /experiments/{run_id}` e `GET /experiments/{run_id}/revisions`;
- tabelas `experiment_runs` e `experiment_run_revisions`;
- `ExperimentRunClient` em `agents/interface.py`;
- regras de revisão: primeira revisão 1, reenvio idêntico idempotente, revisões sequenciais e sem alterar identidade, protocolo, orçamento, métricas já registradas nem avaliação externa.

O trabalho partiu do backend v0.1 (sem autenticação nem migrações Alembic). A v0.2 já grava o `ExperimentRun` no resultado do run (`POST /runs/{run_id}/result`) e o confere com o histórico de tools do servidor. O adaptador do LangGraph grava por um `sink` (`save`/`get`/`update`). Um merge direto daria conflito em `app.py`, `storage.py` e nas migrações.

## Decisão

Portar o trabalho para a v0.2 mantendo o mesmo formato, para que o adaptador e os clientes que já usam essas rotas continuem funcionando:

- **Rotas:** as quatro, com os mesmos caminhos, modelos e códigos (`409 idempotency_conflict`, `404 not_found`, `422` quando o caminho difere do corpo).
- **Regras de revisão:** as do original, em [services/backend/experiments.py](../../services/backend/experiments.py).
- **Tabelas:** as mesmas, pela migração Alembic `0010`, ligadas a `runs` e com instante de gravação.
- **`ExperimentRunClient`:** mesma interface, com `token` e `run_token` opcionais.
- **`ExperimentSink`:** em [agents/compat.py](../../agents/compat.py), implementa o `ExperimentRunSink` do LangGraph sobre essas rotas, dentro da `RunBridge`.

Regras acrescentadas pela v0.2:

- Escrever exige o token do worker e a reserva (`X-Run-Token`) do run de benchmark. Ler exige o operador dono do run ou um worker do mesmo executor com concessão do processo.
- O registro precisa ter o contexto, a tarefa e o executor da reserva, e `verified_success`/`evaluator` nulos.
- `tool_calls` de cada revisão precisa ser igual ao histórico do servidor, com a mesma verificação do resultado (`validate_experiment_history`). O `ExperimentSink` troca as chamadas e os artefatos declarados pelos do cliente comum antes de gravar; o servidor só valida.
- Com revisão gravada, um resultado que traga `experiment` precisa trazer a última revisão. O servidor não preenche o registro sozinho: isso mudaria o hash usado no reenvio idempotente.
- Run encerrado aceita só o reenvio idêntico.

## Consequências

- O LangGraph roda pelo worker v0.2 com `RunBridge` + `ExperimentSink`, sem trocar o adaptador. Quem chamar as rotas diretamente passa a precisar de token e reserva.
- O corte do `ToolClient` para três tools, feito no `856ff06` porque as escritas davam 501 na v0.1, não foi portado: na v0.2 as seis funcionam.
- As revisões ficam no banco e aparecem em `GET /experiments/{run_id}/revisions`; a exportação canônica continua lendo o resultado final.
- Backup e restauração (bloco H) passam a incluir as duas tabelas novas.

Alternativa descartada: manter só o `sink` em memória e ler o registro por `GET /runs/{run_id}`. Descartada porque quebraria quem já usa as rotas do original.

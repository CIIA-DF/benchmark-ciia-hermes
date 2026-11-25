# T0-R2 — Reserva durável antes do domínio

## Escopo e causa

Correção local na worktree oficial team/backend, somente T0-R2 do [plano](../02-arquitetura/backend-plano-lacunas.md). Antes, ToolService usava tool_context para a primeira etapa; esse método consultava o processo antes de reservar. Um version_mismatch ou processo ausente interrompia a chamada sem vínculo lógico, permitindo reutilizar seu ID em outra ferramenta e escapar da contagem de orçamento.

Implementação restrita a services/backend/tools.py e services/backend/execution.py, com testes integrados próprios. T0-R1 preservado; regras específicas de T1/T2, contratos públicos, schema e migrações não foram alterados. T1-R continua pendente: o payload incompleto do processo ainda precisa de validação segura e tentativa auditada.

## Fluxo corrigido

1. Autenticar o ator e validar entrada/identificador conforme os contratos existentes.
2. authorize_tool_context confere run, token/reserva, estado/prazo, contexto e concessões. Para escrita, mantém as releituras/travas de perfis, executor e can_write atuais do T0-R1. Não consulta corpus/processo/checklist.
3. Reservar (run_id, tool_call_id, ferramenta, hash) sob a trava do run e confirmar essa transação.
4. Iniciar a transação do efeito. tool_context repete a autorização técnica e então consulta o processo/domínio.
5. Executar a operação e confirmar sucesso ou fazer rollback. Erro ToolFailure/SQLAlchemy continua sendo auditado em transação própria; a reserva anterior não é desfeita.

Identidade lógica e efeito são duas transações deliberadas. Erro de domínio atribuível à execução mantém o ID e consome orçamento. Mesmo ID com outra ferramenta/entrada é 409 idempotency_conflict; novo ID depois do limite é 409 budget_exceeded. Depois de reparar administrativamente a condição do domínio, repetir a entrada original com o mesmo ID é permitido sem nova cobrança, enquanto a execução/reserva estiver ativa.

Credencial inválida, token de reserva inválido, contexto divergente ou concessão ausente não obtêm reserva lógica nem alcançam o domínio. A recusa ainda pode gerar auditoria quando a reserva identifica legitimamente o run. Caminho de corpo inválido atribuível à reserva, já existente, permanece inalterado.

## Evidências integradas

Novo arquivo tests/backend/test_t0_r2.py:

- Com orçamento 1, processo sintético com versão diferente: chamada retorna 409 version_mismatch, com uma reserva lógica e tentativa correspondente.
- Com orçamento 1, processo/corpus sintético removido (somente dados temporários do teste): chamada retorna 404 not_found, com a mesma garantia de reserva/auditoria.
- Em ambos: reutilizar ID em salvar_minuta gera idempotency_conflict, novo ID gera budget_exceeded e nenhum artefato é produzido.
- Reparo administrativo sintético permite repetir a consulta original com sucesso; continua existindo uma única reserva lógica. Histórico: erro de domínio, conflito de identidade, orçamento excedido, sucesso.
- Observador em conexão independente exige visibilidade da reserva antes de cada chamada ao domínio. Isso verifica commit anterior ao efeito, não apenas inserção seguida de commit posterior.
- Quatro cenários de credencial/reserva/contexto/concessão inválidos instalam sentinela de domínio: exigem 401/403, zero reservas e nenhum acesso ao processo.

A primeira rodada executou também regressões de T0-R1/T0/tentativas: 35 aprovados em SQLite (147,55 s). Depois, os dois cenários de domínio foram reforçados com a observação por outra conexão e repetidos junto às regressões existentes de execução/clientes; resultados finais abaixo.

## Limitações e aceite

Sem migração, mudança de contrato ou alteração de formato JSON. Revisão manual continua conduzida pelo responsável, sem acionamento do Astra. Não houve commit, push, PR ou deploy. Trabalho local anterior preservado.

PostgreSQL não executado porque Docker Linux está parado; visibilidade e travas verificadas somente em SQLite. A suíte completa será repetida no fechamento de T1-R conforme o plano corretivo. Resultados anteriores não substituem o aceite dessa próxima correção. Não se declara T0/T1 globalmente aceitos.


## Fechamento das verificações

- `uv run --locked python -m pytest tests/backend/test_t0_r2.py tests/backend/test_t0_r1.py tests/backend/test_t0.py tests/backend/test_tool_calls.py`: 35 aprovados (147,55 s).
- Após reforçar os dois casos de domínio com observação por conexão independente: `uv run --locked python -m pytest tests/backend/test_t0_r2.py tests/backend/test_execution.py tests/integration/test_adapter_protocol.py`: 27 aprovados (89,36 s).
- As duas rodadas somam 56 testes distintos; os seis testes T0-R2 foram repetidos. Não são 62 testes distintos nem uma execução da suíte completa.
- Ruff e formato sobre todos os arquivos: aprovados. OpenAPI versionado conferido, sem mudança contratual.
- Links/invariantes e diff dirigido aos arquivos T0-R2: aprovados; aviso de depreciação Starlette/HTTPX mantido.
- PostgreSQL não validado (Docker Linux indisponível). Suíte completa prevista no fechamento T1-R; não reutilizar os 123 testes históricos como resultado desta correção.

Estado: implementado e verificado localmente em SQLite. Liberação do responsável e homologação PostgreSQL pendentes; T1-R permanece aberto.

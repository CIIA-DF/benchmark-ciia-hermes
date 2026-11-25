# T0-R1 — Autorização atual na transação da escrita

## Escopo e causa

Correção local da falha de autorização apontada na revisão de D0/T0/T1. Worktree oficial team/backend. Somente o ramo de escrita de ExecutionService.tool_context foi alterado na implementação. O perfil autenticado em actor era um snapshot: owner.can_write era relido, mas worker.can_write vinha desse objeto antigo, permitindo escrita após revogação na janela entre reserva lógica e efeito.

T0-R2 (ordem reserva/domínio) e T1-R (payload incompleto do processo) continuam abertos. Não foram modificados provisionamento/bootstrap, regras específicas de T1/T2 ou contratos públicos. Não houve migração nem alteração de OpenAPI.

## Mudança e fluxo

1. Mantidas as verificações existentes de run, worker titular, token de reserva, estado, prazo, contexto e concessões.
2. Para escrita, reler worker e proprietário na conexão/transação que executará o efeito; não usar actor.can_write como autoridade.
3. Adquirir travas de linha dos dois principals em ordem crescente de principal_id, evitando inversão entre operações. Mantida a trava existente do run.
4. Conferir proprietário operator, worker worker, executor atual compatível com run e can_write atual de ambos.
5. Conferir concessões novamente depois das travas, pois pode ter havido espera por provisionamento que altera perfil e permissões na mesma transação.
6. Manter essas travas até commit/rollback do efeito. Revogação confirmada antes da releitura impede o efeito; alteração administrativa posterior à obtenção da trava é serializada após a transação, sem prometer cancelamento retroativo de escrita já autorizada.
7. Recusa retorna 403 forbidden com o envelope existente. A transação do efeito é revertida; a auditoria de falha fica em transação própria. Reserva lógica já confirmada permanece vinculada; nenhum artefato/recibo de sucesso é emitido.

PostgreSQL usa FOR UPDATE. SQLite utiliza BEGIN IMMEDIATE já existente e serializa escritores no banco; isso não comprova comportamento de travas PostgreSQL.

## Evidências integradas

Novo arquivo tests/backend/test_t0_r1.py, apenas com dados sintéticos. Hook de teste confirma no banco que a reserva lógica já foi commitada, altera o perfil em transação separada e só então chama o escritor original, preservando a janela real do defeito.

- registrar_pendencia e salvar_minuta, revogando can_write do worker e do proprietário: quatro cenários exigem 403, nenhum artifact_id/persisted_at, zero artefatos, uma reserva lógica mantida e tentativa auditada com forbidden.
- Nos mesmos quatro cenários, restauração administrativa explícita permite repetir a operação com o mesmo ID/corpo/chave; depois, replay recupera o artefato original. Histórico esperado: 403/200/200.
- Três cenários adicionais alteram perfil do worker, executor do worker e perfil do proprietário entre reserva e efeito; todos exigem 403, sem artefato e com auditoria.
- Testes existentes de orçamento, concorrência, rollback, migração e recuperação do recibo permanecem preservados.

Resultados: `uv run --locked python -m pytest tests/backend/test_t0_r1.py tests/backend/test_t0.py tests/backend/test_tool_calls.py`: **29 aprovados**, 56,74 s, um aviso de depreciação Starlette/HTTPX. Os sete cenários novos estão incluídos nesses 29.

## Limitações e revisão

Docker Linux segue indisponível: PostgreSQL e seu comportamento concorrente de travas não foram verificados. O código de travas foi revisado, mas não se declara homologação desse banco.

A suíte completa será repetida no fechamento das correções de implementação, conforme o plano; os 123 testes anteriores continuam evidência histórica. Nesta etapa, foram selecionadas também regressões existentes de execução e protocolo por compartilharem o caminho de escrita. Resultados finais desses comandos constam abaixo.

Implementação e verificação SQLite não equivalem a liberação do responsável ou revisão CTO. Astra não foi acionado. Nenhum commit, push, PR ou deploy foi realizado; alterações locais anteriores preservadas. [Plano e pendências](../02-arquitetura/backend-plano-lacunas.md).


## Fechamento das verificações

- `uv run --locked python -m pytest tests/backend/test_execution.py tests/integration/test_adapter_protocol.py`: **21 aprovados**, 78,63 s. Junto aos 29 anteriores, são 50 testes dirigidos em SQLite, não uma execução da suíte completa.
- `uv run --locked python -m ruff check .`: aprovado.
- `uv run --locked python -m ruff format --check .`: aprovado.
- `uv run --locked python -m scripts.export_openapi --check`: cópia coerente, contrato HTTP não alterado.
- `uv run --locked python -m scripts.validate_repository`: links/invariantes aprovados após documentação.
- `git diff --check` dirigido à implementação e documentos T0-R1: sem erros de whitespace.
- Mantido o aviso de depreciação Starlette/HTTPX. PostgreSQL não executado porque o Docker Linux está parado; a suíte completa fica para o fechamento T0-R2/T1-R, conforme o plano corretivo.

Estado final: T0-R1 implementado e verificado localmente; liberação do responsável e homologação PostgreSQL pendentes. Nenhuma afirmação de aceite global de T0/T1 ou de resolução das outras duas falhas.

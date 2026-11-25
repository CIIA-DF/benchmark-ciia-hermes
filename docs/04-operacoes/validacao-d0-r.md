# D0-R — Fichas completas das ferramentas

## Entrega

Correção documental do plano de aceite de D0/T0/T1, na worktree oficial team/backend. [Plano atualizado](../02-arquitetura/backend-plano-lacunas.md#fichas-completas-das-ferramentas--correção-d0-r).

Cada uma das seis tools tem ficha própria com situação atual, entrada/produtor, saída/invariantes, consumidores/fluxo, códigos de resposta, componentes/dependências, mudança restante ou prevista, critérios/evidências e estado de aceite. As fichas referenciam a base T0, sem criar cópias da lógica comum. As ligações de busca para leitura/evidência, checklist para pendência e recibo para artefato/resultado estão explícitas.

## Estado dos achados

- D0: lacuna das fichas atendida documentalmente; liberação manual pendente.
- T0-R1: revogação de can_write do worker na janela reserva/efeito ainda precisa de correção.
- T0-R2: erro de domínio antes da reserva durável ainda precisa de correção.
- T1-R: payload do processo sem requirements_version ainda precisa de tratamento seguro e auditoria.
- T2: implementação preservada e fora do escopo desta correção documental.

Números de testes dos registros anteriores permanecem históricos. Não foram usados para declarar as falhas acima resolvidas. O plano passa a indicar separadamente estado de implementação e pendências de aceite.

## Verificação documental

- Conferência estrutural: seis fichas e nove categorias obrigatórias em cada uma.
- `uv run --locked python -m scripts.validate_repository`: conferência de links e invariantes.
- `git diff --check -- docs/02-arquitetura/backend-plano-lacunas.md docs/04-operacoes/validacao-d0-r.md`: conferência de whitespace.

Nenhum código, contrato executável, schema, teste ou migração foi alterado por D0-R. Não executados testes funcionais, sondas adicionais ou validação PostgreSQL: não houve alteração de comportamento nesta etapa. Histórico de 25/10 e relatório de auditoria de 28/10 não foram modificados. Alterações locais anteriores preservadas. Sem commit, push, PR, implantação ou revisão automática/Astra.

Próxima etapa: T0-R1, após liberação do responsável conforme a execução por etapa acordada.

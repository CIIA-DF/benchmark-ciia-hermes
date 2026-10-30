# Runbooks

- [Validação do bloco 1 em 25/10/2026](validacao-bloco1-2026-10-25.md): snapshots coerentes, falhas no chat, reconexão limitada e heartbeat.

- [Correções de streaming e polling em 25/10/2026](correcoes-streaming-worker-2026-10-25.md): comportamento e validação dos dois apontamentos.

- [Validação do backend em 24/10/2026](validacao-backend-2026-10-24.md): evidências locais e limites.

- [Chat, tools e execuções](chat.md): inicialização, perfis, streaming e integração dos agentes.

- [Integração dos agentes](integracao-agentes.md): catálogo, fábrica e homologação.
- [Governança GitHub](github-governance.md): branches, revisão e checks.
- [Atualização manual das equipes](../00-comece-aqui/02-fluxo-git.md): fetch, merge, conflitos e preservação do trabalho.
- [Operação local](operations.md): saúde, logs e persistência.
- [Backup/restauração](backup-restore.md): cópia binária e restauração isolada.
- [Hostinger e rollback](deploy-vps-hostinger.md): configurar, aprovar, implantar e recuperar.

- [Auditoria de Backend & Tools em 28/10/2026](auditoria-backend-2026-10-28.md): inventário, catálogo de respostas, tipagem, segurança e pendências reproduzíveis.

- [T0 em 28/10/2026](validacao-t0-2026-10-28.md): identidade durável das chamadas, orçamento, validação de saída e recuperação de recibo.

- [T1 em 28/10/2026](validacao-t1-2026-10-28.md): coerência de consultar_processo, inventário e contexto recebido pelo cliente.

- [T2 em 28/10/2026](validacao-t2-2026-10-28.md): busca literal, escopo, limites, integridade do índice e portabilidade Unicode.

- [T0-R1](validacao-t0-r1.md): revogação de escrita na janela reserva/efeito, travas e auditoria nas duas tools.

- [T0-R2](validacao-t0-r2.md): commit da identidade lógica antes do domínio, orçamento de falhas e recuperação da operação original.

- [T1-R](validacao-t1-r.md): payload de processo inválido, erro seguro, reserva preservada e auditoria nas seis tools.

- [T3](validacao-t3.md): identidade do documento, páginas exatas/ordenadas e leitura integral/parcial nos clientes.

- [T4](validacao-t4.md): checklist versionado, IDs únicos, erros seguros e fluxo para pendência.

- [T5](validacao-t5.md): requisito/fontes, efeito/recibo, replay, rollback e recuperação pós-commit da pendência.

- [T6](validacao-t6.md): minuta, contexto/hash nos clientes, fontes e recuperação do escritor comum.

- [F0](validacao-f0.md): tentativas físicas e fases, migração aditiva e preservação do histórico legado.

- [F1](validacao-f1.md): consultar_processo, contratos preservados e correspondência de reservas/tentativas F0.

- [F2](validacao-f2.md): rejeição explícita de NUL na busca, contrato público e auditoria de entrada recusada.

- [F3](validacao-f3.md): leitura integral/parcial, páginas exatas e rastreamento F0.

- [F4](validacao-f4.md): checklist versionado, rastreamento F0 e consumo autorizado na pendência.

- [F5](validacao-f5.md): pendência com F0 e validador de integridade reutilizável, preservando o GET.

- [F6 e fechamento F](validacao-f6.md): minuta após F5, matriz individual e suíte completa.

- [A0](validacao-a0.md): envelopes HTTP seguros, challenge Bearer, no-store, corpo de 1 MiB e erros SSE.

- [A1](validacao-a1.md): GET de artefatos com integridade F5, autorização preservada e testes dirigidos com duração.

- [A2](validacao-a2.md): resultado experimental reconciliado com chamadas/efeitos, incerteza de transporte e testes dirigidos.

- [A3](validacao-a3.md): quota queued por operador em POST /runs, replay anterior à quota e concorrência entre aplicações.

- [A4](validacao-a4.md): quatro APIs de conversas, quota comum chat/benchmark, isolamento, memória e atomicidade.

- [A5](validacao-a5.md): expiração queued em GET/criação/claim, queue_timeout e preservação de parciais/artefatos.

- [A6](validacao-a6.md): claim exclusivo e presença durável, inclusive em polling vazio autorizado.

- [A7](validacao-a7.md): heartbeat com presença e lease atômicos, perfil atual e disputas terminais.

- [A8](validacao-a8.md): teto de 20.000 eventos, vaga terminal, rollback de efeitos e recuperação com pool limitado.

- [A9](validacao-a9.md): cinco admissões SSE duráveis por operador, recuperação por TTL e liberação no ciclo ASGI.

- [A10](validacao-a10.md): configuração habilitada separada da presença autorizada nos últimos 60 s e modelo desconhecido explícito.

- [A11](validacao-a11.md): consulta SQL real no health, 200/503 seguros e alcance explícito.

- [A12](validacao-a12.md): identidade e estrutura dos processos listados, envelope seguro e vazio autorizado.

- [A13](validacao-a13.md): seis fronteiras HTTP, executor compatível e teto de 1.000 admissões físicas por run, sem apagar recusas.

- [Fechamento A](validacao-a-fechamento.md): matriz A0–A13, workflow, contratos públicos, limites e validação consolidada.

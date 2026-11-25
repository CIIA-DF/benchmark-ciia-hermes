# Estado atual do Backend & Tools

Consolidação documental: 31/10/2026; atualização E em 02/11/2026; port do LangGraph (J) em 21/11/2026, worktree oficial `team/backend`. Este índice é o ponto de entrada atual; relatórios vinculados preservam a data, o código avaliado e suas limitações.

## Referências de consumo

- [API vigente: 26 operações, erros, limites e exemplos](../02-arquitetura/backend-api-atual.md). As quatro de `/experiments` vieram do port de 21/11/2026 ([ADR 011](../05-decisoes/011-registro-experimental-revisoes.md)); `GET /ready` (schema na revisão esperada) foi acrescentada no mesmo dia.
- [Contratos e histórico de compatibilidade](../../contracts/README.md).
- [Operação do chat](chat.md) e [integração de agentes](integracao-agentes.md).
- [Decisão documental e versões](../05-decisoes/010-documentacao-interfaces.md).
- [Plano por blocos](../02-arquitetura/backend-plano-blocos.md).

## Implementação, verificação e liberação

| Tema | Implementação local | Evidência de verificação | Liberação |
| --- | --- | --- | --- |
| F — ferramentas | Seis tools, reserva lógica, tentativas físicas e integridade | [F0](validacao-f0.md), [F1](validacao-f1.md), [F2](validacao-f2.md), [F3](validacao-f3.md), [F4](validacao-f4.md), [F5](validacao-f5.md), [F6](validacao-f6.md) | Revisão conjunta e PostgreSQL não substituídos por SQLite |
| A — APIs | A0–A13 locais | [Fechamento A](validacao-a-fechamento.md): 390 casos históricos; auditoria posterior neste chat: 119 casos e achado A7 | A7 condicionado à revisão da correção; homologação global pendente |
| A7 — correção temporal | Revalidação de prazo após travas/concessões presente no código local | [Registro A7](validacao-a7.md); D não transforma implementação em novo aceite comportamental | Revisão manual e espera real por trava em PostgreSQL pendentes |
| I — clientes, identidade e transporte | I1–I3 locais; bootstrap preserva principais; rotação explícita; limites do proxy | [Fechamento I](validacao-i-fechamento.md): 454 casos na suíte compartilhada e quatro novos por complemento dirigido; não uma suíte única de 458 | Agentes reais e cadeia Nginx/Compose não homologados |
| D — documentação | Referência, índice, migrações, ADR e exemplos consolidados | [Validação D](validacao-d.md) | Disponível para revisão manual; sem aceite automático das equipes |
| E — exportação | JSONL v2 pelo histórico persistido; declarado/observado/avaliado separados | [Validação E](validacao-e.md): reconciliação direta com SQL, falhas/retries, legado e snapshot | Revisão de consumidores e PostgreSQL pendentes |
| J — registro experimental do LangGraph | Port das rotas `/experiments`, revisões, `ExperimentRunClient` e `ExperimentSink` (João Enomoto, `856ff06`); `GET /ready`; `scripts.benchmark_batch`; revisões na exportação | [Validação J](validacao-j.md): testes dirigidos e conferência com o adaptador LangGraph real usando modelo falso | Revisão do LangGraph e da Metodologia; LLM real e PostgreSQL pendentes |
| K — alinhamento com as frentes | Catálogo comum `openai_tools()`/`catalog_version()`; patches propostos ao Hermes (cliente injetado e metadados da reserva) e teste ponta a ponta do LangGraph | [Validação K](validacao-k.md): Hermes com patch pela `RunBridge`, LangGraph 10/10, Evaluation 16/16 sobre a v0.2, com modelos falsos | Adoção do catálogo e dos patches pelas equipes; caminho entre JSONL v2 e métricas com a Metodologia |
| S — dependências | S1: certifi 2026.11.20 e opentelemetry-api 1.45.2 no lock (22/11/2026). S2: Next 14.2.35 do portal só registrado, com alvo proposto | [S1/S2](validacao-s1-s2.md): sync, lint, links, OpenAPI e testes rápidos; suíte completa pendente | S2 com a frente do portal; sem exposição compartilhada do portal até a correção |
| O — indicadores | Proposta no plano | Sem análise experimental de ganhos comprovada nesta entrega | Pendente |
| H — homologação | SQLite disponível | PostgreSQL, backup/restauração e infraestrutura real não comprovados | Pendente |

Contagens de seleções têm interseção: não somar testes dirigidos à suíte. Evidência histórica não comprova alterações posteriores. Metadados de schema e docstrings adicionados localmente não provam que um modelo remoto os recebeu.

## Migrações e atualização de base

| Revisão | Finalidade |
| --- | --- |
| 0001 | Corpus: processos, documentos e chunks |
| 0002 | Identidades/concessões, conversas, mensagens, runs, eventos e artefatos |
| 0003 | Identificador de participante nas conversas |
| 0004 | Ledger legado `tool_calls` |
| 0005 | Identidade durável `logical_tool_calls` |
| 0006 | Tentativas físicas e fases; sem inferir requisições antigas |
| 0007 | Presença de worker; sem observação retroativa inventada |
| 0008 | Leases duráveis de SSE |
| 0009 | Eventos administrativos; sem credenciais nem histórico retroativo inventado |
| 0010 | Registro experimental (`experiment_runs` e `experiment_run_revisions`), portado do LangGraph; sem registros inferidos para runs anteriores ([ADR 011](../05-decisoes/011-registro-experimental-revisoes.md), [J](validacao-j.md)) |

Fontes: [revisões Alembic](../../migrations/versions) e [migração do backend](../../services/backend/migrate.py). Aplicar o fluxo documentado em [chat](chat.md) e [scripts](../../scripts/README.md), com backup e restauração isolada antes de base relevante. Não editar revisão publicada nem usar `create_all` como substituto de upgrade. D não executou migração em base operacional.

A trilha administrativa registra estados e operações; não comprova identidade humana nem resiste ao administrador do banco. Bootstrap só cria ausentes. Atualizações/rotação são explícitas; rotação preserva concessões e permissões por padrão. [Evidências I2](validacao-i2.md).

Backup/restauração em H deve incluir corpus, perfis/concessões, runs/mensagens/eventos, artefatos, chamadas lógicas, tentativas/fases, presença, leases, trilha administrativa e registros experimentais com suas revisões. Procedimento publicado não equivale a restauração já validada.

## Histórico e pendências

A [referência pré-D](../02-arquitetura/backend-api.md), auditorias T/F/A/I e ADRs anteriores ficam preservados. Não mover ou apagar evidências para esconder mudança de comportamento. O [levantamento documental](levantamento-documentacao-backend.md) continua registrando sua origem; consolidação física de todos os relatórios não é requisito de D.

Não há autorização de commit, PR, deploy ou uso compartilhado concedida por este índice. Aprovação manual continua independente da execução e da documentação local.

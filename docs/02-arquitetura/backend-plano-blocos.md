# Plano de implementação por blocos — Ferramentas, APIs e Backend

## Blocos pendentes

Observação para a entrega na branch `team/backend`: os blocos F e A têm fechamento técnico local em SQLite.
Os blocos **I, D, E, O e H permanecem pendentes**, conforme o plano fornecido pelo responsável.
Publicar a branch não equivale à conclusão do plano, ao aceite global ou à autorização de deploy.
Relatórios, propostas e atualizações incrementais de documentação não encerram os blocos abaixo.

| Bloco | Trabalho restante |
| --- | --- |
| I — Integrações | I1: clientes/protocolo e retries; I2: bootstrap, provisionamento, rotação e revogações; I3: transporte, proxy e ambiente |
| D — Documentação formal | Consolidar endpoints, contratos, exemplos, ADRs, migrações, versões e estado verificado/proposto após formalizar as interfaces |
| E — Exportação canônica | Exportar do histórico persistido, reconciliar IDs/tentativas/fases/efeitos, distinguir declarado/observado/avaliado e versionar legados |
| O — Observabilidade | Definir indicadores reproduzíveis, correlação segura e análise sintética que sustente decisões sem inventar ganhos reais |
| H — Homologação | Validar PostgreSQL, concorrência, travas, quotas, busca, migrações, atualização de base existente, backup e restauração |

A aprovação final permanece manual. PostgreSQL e recuperação documentada são requisitos do aceite global.
As seções originais abaixo preservam o detalhamento e os critérios de aceite de cada bloco.

## 1. Organização e regras de execução

**Objetivo:** corrigir os achados da auditoria, preservar compatibilidade e produzir evidências confiáveis para avaliar ferramentas e resultados experimentais.

**Ordem obrigatória:**

**Ferramentas → APIs por endpoint → Integrações → Documentação das APIs → Exportação → Observabilidade → Homologação.**

- Trabalhar exclusivamente na worktree oficial `backend-tools`, branch `team/backend`, preservando alterações existentes.
- Executar um sub-bloco de cada vez. Não misturar correções de ferramentas, autenticação, exportação e infraestrutura na mesma entrega.
- Cada sub-bloco terá causa, alterações, consumidores afetados, testes, resultados e limitações registrados.
- Cada bloco principal termina com revisão manual do responsável antes do seguinte.
- Conforme definido, SQLite permite revisão local; PostgreSQL pendente será explicitado e continuará obrigatório para o aceite global.
- Os **219 testes aprovados são a referência inicial**, não evidência antecipada das próximas alterações.
- Sem commit, publicação, promoção para produção ou revisão automática por outros agentes.

**Regra de compatibilidade:** mudanças mínimas nos modelos e consumidores diretamente afetados pertencem à mesma entrega da mudança funcional. A revisão ampla das integrações fica no bloco próprio. OpenAPI acompanha mudanças executáveis; a consolidação editorial da documentação ocorre depois da formalização.

## 2. Bloco F — Ferramentas, uma por vez

### F0 — Base compartilhada de rastreamento

**Local:** `ToolService`, escritor transacional, histórico e modelos de persistência.

Corrigir primeiro a estrutura compartilhada necessária para que as seis ferramentas tenham a mesma definição de tentativa:

- Manter a identidade lógica por `run_id + tool_call_id`, vinculada à ferramenta e ao hash dos argumentos.
- Criar identidade de tentativa física gerada pelo servidor para cada requisição recebida.
- Vincular as fases da execução à mesma tentativa: início, efeito confirmado e conclusão/falha.
- Separar resultado do efeito e resposta HTTP. Commit confirmado não significa resposta recebida pelo cliente.
- Preservar registros antigos como histórico legado, sem inferir retroativamente quantas requisições ocorreram.
- Aplicar migração aditiva após a última revisão existente; não reescrever migrações publicadas.
- Manter reserva lógica antes do domínio, auditoria após rollback e idempotência das escritas.

**Aceite:** falha na releitura pós-commit seguida de retry produz **duas tentativas físicas, um artefato e fases corretamente relacionadas**. A resposta efetivamente recebida pelo cliente permanece desconhecida quando não houver evidência.

### F1 — `consultar_processo`

**Local:** leitura de processo/inventário, contrato de retorno e consumidor compartilhado.

- Integrar o rastreamento de F0.
- Preservar validação de processo, identidade, versão e inventário.
- Não alterar a regra de negócio já corrigida sem nova falha reproduzida.

**Aceite:** inventário vazio com 200; processo ausente com 404; versão divergente com 409; payload inconsistente com 500 seguro; reserva e tentativa coerentes.

### F2 — `buscar_documentos`

**Local:** `SearchInput`, consulta do corpus e validação do resultado.

- Rejeitar explicitamente U+0000 com `422 validation_error`.
- Não remover o caractere silenciosamente nem ampliar a consulta.
- Preservar busca literal de `%` e `_`, limite, ordenação e isolamento por processo/corpus.
- Registrar a entrada recusada conforme as regras de atribuição e orçamento existentes.

**Aceite:** NUL não executa busca bem-sucedida; testes de Unicode, caracteres especiais, resultados vazios e isolamento passam. Comparação SQLite/PostgreSQL permanece identificada.

### F3 — `ler_documento`

**Local:** leitura do corpus, `DocumentResult` e validação dos clientes.

- Integrar F0 e preservar a implementação T3.
- Conferir documento, contexto, páginas exatas, ordem e hash integral.
- Manter leitura parcial explicitamente distinta de comprovação de completude do arquivo original.

**Aceite:** páginas não contíguas, seleção parcial, documento ausente e respostas adulteradas continuam tratados corretamente.

### F4 — `consultar_requisitos`

**Local:** consulta do checklist, `RequirementsResult` e consumidor.

- Integrar F0 e preservar T4.
- Conferir identidade, versão, unicidade e checklist não vazio.
- Manter ausência, corrupção e indisponibilidade como situações distintas.

**Aceite:** 200/404/500/503 corretos; isolamento de versão; jornada checklist → pendência sem aceitação de requisito estrangeiro.

### F5 — `registrar_pendencia`

**Local:** ramo de pendência no escritor compartilhado e validação de recibos.

- Aplicar o rastreamento corrigido ao fluxo de requisito, evidência, efeito e recibo.
- Preservar revalidação de permissões, integridade persistida, rollback e replay.
- Extrair ou ajustar a validação compartilhada de integridade para permitir reutilização posterior pelo GET de artefato, sem alterar esse endpoint neste sub-bloco.

**Aceite:** concorrência produz um artefato; falha anterior ao commit não deixa efeito; falha posterior preserva efeito e permite replay; tentativa física não é duplicada pelas fases.

### F6 — `salvar_minuta`

**Local:** ramo de minuta no escritor e validação dos clientes síncrono/assíncrono.

- Aplicar a mesma correção de rastreamento.
- Preservar validação de conteúdo, evidências, contexto e hash.
- Não introduzir dependência obrigatória de checklist ou pendência.

**Aceite:** busca → leitura → minuta funciona; ambos os clientes recusam recibo adulterado; concorrência e recuperação mantêm um único efeito.

### Fechamento do bloco F

- Executar regressões das seis ferramentas, migração, autorização, orçamento, replay, rollback e perda de resposta.
- Conferir reservas, tentativas e artefatos diretamente no banco.
- Executar a suíte completa.
- Entregar matriz individual de implementação, verificação e pendências.
- Solicitar liberação manual antes de iniciar APIs.

## 3. Bloco A — APIs, endpoint por endpoint

### A0 — Comportamento HTTP compartilhado

Tratar exclusivamente a fronteira HTTP:

- Uniformizar erros de domínio, framework e validação de saída em envelope seguro.
- Preservar status e cabeçalhos pertinentes, incluindo `Allow` em 405.
- Acrescentar challenge Bearer em 401 e `no-store` nas respostas autenticadas.
- Aplicar limite de corpo de **1 MiB**, inclusive com transferência em partes.
- Não converter indiscriminadamente exceções internas em erros de validação.
- Testar separadamente erros anteriores e posteriores à abertura de SSE.

### A1 — `GET /artifacts/{id}`

- Reutilizar a validação de integridade preparada no bloco F.
- Conferir ferramenta, payload, recibo, contexto do run, identificadores e hashes.
- Retornar `500 invalid_response` seguro para corrupção.
- Preservar propriedade, concessões e comportamento de recurso ausente.

**Aceite:** adulterações de ambas as ferramentas de escrita deixam de retornar sucesso.

### A2 — `POST /runs/{id}/result`

- Confrontar chamadas declaradas com identidades e resultados observados.
- Recusar chamadas inventadas, ferramentas divergentes e artefatos incompatíveis.
- Exigir correspondência das chamadas lógicas atribuíveis ao run; manter falhas de transporte e ausência de resposta distinguíveis de execução inexistente.
- Preservar relato do agente separado do histórico observado e da avaliação independente.
- Não usar igualdade de duração cliente/servidor como critério.
- Preservar consistência com deltas e repetição idempotente do resultado.

**Aceite:** a sonda `never-executed` é recusada; resultados legítimos com retry e efeito pós-commit continuam representáveis.

### A3 — `POST /runs`

- Implementar limite de **20 execuções queued por operador**, conforme o plano existente.
- Verificar replay antes da aplicação da quota.
- Preservar isolamento, contexto e atomicidade.
- Garantir que a concorrência não ultrapasse o limite.

### A4 — APIs de conversas

Tratar e verificar separadamente:

| Endpoint | Alteração ou verificação |
|---|---|
| `POST /conversations` | Preservar escopo autorizado e validação de contexto/executor. |
| `GET /conversations` | Verificar isolamento por proprietário e filtros. |
| `GET /conversations/{id}` | Conferir memória, execuções e respostas sob o contrato HTTP corrigido. |
| `POST /conversations/{id}/messages` | Aplicar quota comum de fila, replay anterior à quota e atomicidade mensagem/run; preservar uma execução ativa por conversa. |

Não acrescentar paginação ou redesenhar memória sem um requisito específico.

### A5 — `GET /runs/{id}`

- Tornar observável a expiração de queued após **300 segundos**.
- Registrar estado terminal e causa específica de timeout da fila.
- Preservar resultados parciais, histórico e artefatos.
- Aplicar a mesma regra de expiração aos caminhos de criação e claim, evitando dependência exclusiva de consultas do operador.

### A6 — `POST /runs/claim`

- Preservar claim exclusivo, escopo do worker e 204 sem trabalho.
- Não entregar execução expirada na fila.
- Registrar presença do worker, inclusive em polling válido sem trabalho.

### A7 — `POST /runs/{id}/heartbeat`

- Atualizar presença observada e lease somente para worker autorizado.
- Preservar incompatibilidade de executor e recusa de lease inválido.
- Verificar concorrência com expiração e finalização.

### A8 — `POST /runs/{id}/events`

- Preservar tipos e idempotência de eventos.
- Implementar teto de **20.000 eventos por run**.
- Reservar capacidade para registrar o encerramento por limite.
- Manter um único desfecho terminal, sem ciclos de erro.

### A9 — `GET /runs/{id}/events`

- Implementar limite de **5 conexões SSE por operador**, com controle durável entre processos e recuperação de leases abandonados.
- Preservar cursor, reconexão, ordenação e reautorização.
- Garantir liberação da conexão em término, erro ou desconexão.
- Preservar `stream_error` depois da abertura do stream.

### A10 — `GET /capabilities`

- Separar configuração habilitada de presença observada.
- Considerar worker recente dentro da janela de **60 segundos**.
- Representar modelo/configuração desconhecidos explicitamente.
- Atualizar consumidores diretamente afetados; não redefinir silenciosamente o significado do campo legado `available`.

### A11 — `GET /health`

- Manter verificação real de banco com 200/503.
- Não apresentar esse endpoint como prova de funcionamento de worker ou LLM.

### A12 — `GET /processos`

- Conferir escopo autorizado e validação do payload de saída.
- Aplicar o envelope seguro para inconsistência persistida.
- Preservar listagem vazia válida.

### A13 — Rotas HTTP das seis ferramentas

Verificar individualmente `/tools/consultar_processo`, `/tools/buscar_documentos`, `/tools/ler_documento`, `/tools/consultar_requisitos`, `/tools/registrar_pendencia` e `/tools/salvar_minuta`.

- Validar autenticação, lease, identidade lógica, cabeçalhos, limites e envelopes após A0.
- Aplicar teto de **1.000 tentativas físicas por run**, preservando identidade e registros existentes.
- Não repetir mudanças de regra de negócio já encerradas no bloco F.

### Fechamento do bloco A

Executar testes por endpoint, contratos, autorização cruzada e suíte completa. Registrar mudanças públicas de campos, códigos, limites e estados para revisão manual.

## 4. Blocos I e D — Integrações e documentação formalizada

### I1 — Conexão entre agentes, clientes e ferramentas

**Tema exclusivo:** clientes síncrono/assíncrono e protocolo compartilhado.

- Validar consumo de todos os contratos formalizados nos blocos anteriores.
- Preservar o mesmo ID lógico, corpo e chave de idempotência durante retry.
- Separar ID lógico de tentativa física.
- Não repetir automaticamente resposta de sucesso inválida.
- Testar timeout, perda de resposta, conflito, quota e revogação.
- Preservar execução paralela quando permitida, sem impor cadeia fixa de ferramentas.

**Aceite:** os dois clientes apresentam comportamento equivalente e não duplicam efeitos.

### I2 — Conexão com ambiente e identidade administrativa

**Tema exclusivo:** bootstrap, provisionamento e rotação.

- Bootstrap cria somente principais ausentes.
- Atualizações exigem operação administrativa explícita.
- Rotação de token preserva permissões e concessões por padrão.
- Revogações sobrevivem a reinícios e repetição do setup.
- Auditar operações administrativas sem registrar credenciais.

**Aceite:** reproduzir revogação → reinício → nova tentativa, mantendo a recusa.

### I3 — Transporte e ambiente de execução

**Tema exclusivo:** configuração de conexão e proxy.

- Validar timeouts, encaminhamento de cabeçalhos e comportamento SSE.
- Conferir limite de corpo no backend e no proxy.
- Preservar segredos fora de logs.
- Usar doubles para falhas controladas; identificar separadamente a homologação dos runtimes reais.

### D — Documentação das APIs

Iniciar a consolidação após a formalização e verificação das interfaces.

- Atualizar referência de cada endpoint: autenticação, entradas, saídas, erros, cabeçalhos, limites e exemplos.
- Documentar identidade lógica, tentativa física, fases, efeito persistido e resposta HTTP.
- Explicar configuração versus presença e health versus prontidão.
- Atualizar migrações, ADRs e versões de API, pacote de contratos e envelope experimental.
- Manter registro de implementação, verificação e liberação separados.
- Preservar documentos históricos e acrescentar índice do estado atual.
- Validar OpenAPI, exemplos, links e consumidores.

**Aceite:** a documentação descreve o comportamento verificado e identifica explicitamente o que permanece proposto.

## 5. Demais blocos, separados por tema

### E — Exportação canônica

- Substituir reconstrução por SSE pela leitura do histórico persistido.
- Exportar identidades, tentativas, fases, códigos, replay e efeitos.
- Preservar falhas posteriores ao encerramento.
- Separar dados declarados, observados e avaliados.
- Versionar a exportação; identificar registros legados sem precisão suficiente.
- Manter conteúdo opt-in e valores desconhecidos como `null`.

**Aceite:** reconciliar banco e arquivo exportado por IDs, contagens e artefatos, incluindo falhas e retries.

### O — Observabilidade para decisões

- Criar dicionário de indicadores com unidade, numerador, denominador, origem e limitações.
- Medir sucesso lógico, erro por tentativa física, recuperação por retry e efeito confirmado separadamente.
- Acrescentar correlação segura às falhas de coleta.
- Não somar durações paralelas como latência total.
- Não tratar HTTP 200 como sucesso metodológico nem ausência de dado como zero.
- Produzir análise sintética demonstrando como um indicador leva a uma ação de melhoria; ganhos reais dependerão de experimento posterior.

**Aceite:** cada indicador pode ser reproduzido a partir da exportação e explicita lacunas de coleta.

### H — Homologação de banco e recuperação

- Executar cenários pertinentes em PostgreSQL.
- Validar concorrência, travas, quotas, migrações e semântica de busca.
- Exercitar backup e restauração das tabelas de domínio, identidades, tentativas, fases, eventos e artefatos.
- Verificar atualização de base existente sem perda do histórico.

**Aceite:** evidências PostgreSQL e recuperação documentadas antes do aceite global.

### Encerramento global

Entregar relatório consolidado com achados resolvidos, testes, compatibilidade, documentação atualizada e limitações restantes. Novos achados serão registrados no tema correspondente, sem incorporá-los silenciosamente a uma entrega em andamento.

A aprovação final permanece manual e não implica autorização de deploy.

## Registro de execução F0

F0 implementado e verificado localmente em SQLite: 231 testes na suíte completa, incluindo os 12 cenários novos; execução dirigida final com 12 aprovados. Migração aditiva 0006, sem backfill ou alteração de histórico legado. [Evidências F0](../04-operacoes/validacao-f0.md) e [ADR 008](../05-decisoes/008-tentativas-fisicas-tools.md). PostgreSQL e aceite manual pendentes; F1 aguarda liberação específica.


## Registro de execução F1

Integração existente de consultar_processo com F0 preservada e verificada: 50 testes dirigidos aprovados em SQLite (oito novos cenários F1 e 42 regressões pertinentes), 217,78 s. Lint/formato, OpenAPI, documentação e diff aprovados. Suíte completa histórica F0 de 231 testes não repetida nesta entrega sem alteração de produção. Sem alteração funcional, schema ou migração. [Evidências F1](../04-operacoes/validacao-f1.md). PostgreSQL e revisão manual pendentes; F2 aguarda liberação.


## Registro de execução F2

SearchInput.query rejeita U+0000 com 422 antes da consulta; padrão refletido no OpenAPI e catálogo. Busca e política de atribuição/orçamento preservadas. Verificação dirigida: 44 aprovados em SQLite (nove novos e 35 regressões), 252,01 s; lint/formato, OpenAPI, documentação e diff aprovados; [evidências F2](../04-operacoes/validacao-f2.md). PostgreSQL e revisão manual pendentes; F3 aguarda liberação.


## Preferência de relatórios

Relatórios completos adotam redação concisa solicitada pelo responsável. Preservar fatos técnicos, comandos, resultados, limitações e gramática clara.

## Registro de execução F3

Integração T3/F0 preservada e verificada: 40 testes dirigidos aprovados em SQLite, 206,68 s; nove novos e 31 regressões. Lint, formato, documentação, OpenAPI e diff aprovados. Suíte completa não repetida nesta entrega de testes/documentação. Sem alteração funcional ou de schema. [Evidências F3](../04-operacoes/validacao-f3.md). PostgreSQL e aceite manual pendentes; F4 aguarda liberação.


## Registro de execução F4

Integração T4/F0 preservada e verificada: 36 testes dirigidos aprovados em SQLite, 154,75 s; sete novos e 29 regressões. Lint, formato, documentação, OpenAPI e diff aprovados. Suíte completa não repetida nesta entrega de testes/documentação. Sem alteração funcional ou de schema. [Evidências F4](../04-operacoes/validacao-f4.md). PostgreSQL e aceite manual pendentes; F5 aguarda liberação.


## Registro de execução F5

Validação de integridade extraída para função reutilizável com contexto confiável; fachada do escritor e GET preservados. Hash canônico movido sem alteração do algoritmo ou de execution.digest. Prova antes/depois aprovada (três casos em cada rodada); regressões dirigidas finais: 57 aprovados em SQLite, 272,07 s, incluindo cinco casos novos. Lint, formato, documentação, OpenAPI e diff aprovados. Suíte completa prevista no fechamento principal F. [Evidências F5](../04-operacoes/validacao-f5.md). PostgreSQL e aceite manual pendentes; F6 aguarda liberação.


## Registro de execução F6 e fechamento F

Dois cenários novos aprovados em SQLite, 18,39 s. Jornada e concorrência da minuta preservadas após F5. Fechamento local F0–F6: 271 testes aprovados em SQLite, 893,63 s; lint/formato e validação do repositório aprovados. OpenAPI e diff conferidos. [Matriz individual e evidências F6](../04-operacoes/validacao-f6.md). PostgreSQL e revisão manual pendentes. APIs não iniciadas; A0 depende de liberação explícita após revisão do bloco F.

## Registro de execução A0 — 30/10/2026

Pedido explícito “Faça A0” autoriza a implementação local da fronteira HTTP.
Envelopes de framework/saída/erro interno, challenge, no-store, limite de 1 MiB e ciclo SSE implementados.
Execução dirigida: 26 aprovados; [relatório A0](../04-operacoes/validacao-a0.md).
Verificação ampliada registrada no relatório. PostgreSQL e revisão manual permanecem pendentes.
A1 não iniciado. Histórico F preservado; solicitação A0 não presume revisão CTO/Astra concluída.

Resultado final A0: `scripts.dev check` aprovado, 283 testes SQLite em 1.548,55 s; lint, formato e validação do repositório aprovados. OpenAPI conferido.
Metadados Git em D: indisponíveis após retomada; conferência final de diff pendente. PostgreSQL e revisão manual continuam pendentes.

## Registro de execução A1 — 30/10/2026

GET de artefatos adota o validador F5 com contexto confiável do run e saída ArtifactResponse tipada.
Propriedade/grants e recusas anteriores preservados. Corrupção de ambas as escritas reproduzida antes e recusada após a correção.
Verificação dirigida: 14 aprovados em SQLite, 94,72 s; seis casos próprios e oito próximos.
Suíte completa reservada ao fechamento A por pedido explícito. [Relatório A1](../04-operacoes/validacao-a1.md).
PostgreSQL e revisão manual pendentes. A2 não iniciado.

## Registro de execução A2 — 30/10/2026

Finalização experimental confronta declarações com reservas, tentativas atribuídas, ledger legado e efeitos/artefatos.
Sonda never-executed reproduzida com 200 antes da correção e recusada após. Transporte, efeito pós-commit, deltas e replay preservados.
Verificação dirigida: 19 casos distintos em SQLite; 17 aprovados na seleção inicial e duas sondas pós-commit corrigidas/aprovadas na repetição.
Tempos: 56,49 s e 12,31 s; não somar repetições como testes novos. [Relatório A2](../04-operacoes/validacao-a2.md).
Suíte completa no fechamento A, conforme pedido. PostgreSQL e revisão manual pendentes. A3 não iniciado.

## Registro de execução A3 — 30/10/2026

POST /runs aplica padrão de 20 queued por operador sob a trava do principal; RUN_MAX_QUEUED_PER_OPERATOR positivo permite configuração.
Replay precede quota; sem capacidade, 429 resource_limit. Contagem considera chat/benchmark, mas aplicação ao produtor de mensagens fica em A4.
Verificação: 12 dirigidos aprovados em SQLite, 31,17 s; sete próprios e cinco próximos, incluindo duas aplicações disputando a última vaga.
[Relatório A3](../04-operacoes/validacao-a3.md). Suíte completa reservada ao fechamento A.
PostgreSQL e revisão manual pendentes. A4 não iniciado.

## Registro de execução A4 — 30/10/2026

Quota A3 agora é comum ao POST /runs e ao envio de mensagens, na mesma transação e sob a trava do operador.
As quatro APIs de conversas foram verificadas separadamente quanto a escopo, filtros, respostas, memória e gravação atômica.
Verificação dirigida: 17 aprovados em SQLite, 83,43 s; nove próprios e oito próximos, incluindo disputas chat/benchmark e entre conversas.
[Relatório A4](../04-operacoes/validacao-a4.md). Sem paginação ou redesenho de memória.
Suíte completa reservada ao fechamento A. PostgreSQL e revisão manual pendentes. A5 não iniciado.

## Registro de execução A5 — 30/10/2026

Queued expira passivamente após 300 s desde created_at, configurável por RUN_QUEUE_TIMEOUT_SECONDS positivo, com timed_out/queue_timeout e evento done atômico.
GET, criação e claim processam a regra; quota/claim revalidam sob trava. Históricos, parciais e artefatos preservados; running mantém worker_timeout.
StoredResult e rótulo do portal atualizados; causa reservada não pode ser enviada pelo worker.
Verificação: 18 dirigidos aprovados em SQLite, 112,98 s; dez próprios e oito próximos. Lint/tipagem do consumidor do portal aprovados.
[Relatório A5](../04-operacoes/validacao-a5.md). Suíte completa reservada ao fechamento A.
PostgreSQL e revisão manual pendentes. A6 não iniciado.

## Registro de execução A6 — 30/10/2026

Claim preserva exclusividade, grants, fila vencida e 204. Migração 0007 registra presença durável por worker, inclusive polling vazio autorizado.
6 testes dirigidos aprovados em SQLite em 34,91 s. [Relatório A6](../04-operacoes/validacao-a6.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A7 — 30/10/2026

Heartbeat revalida perfil/executor/credencial, atualiza presença e lease atomicamente e não ressuscita estado terminal.
10 testes dirigidos aprovados em SQLite em 32,91 s. [Relatório A7](../04-operacoes/validacao-a7.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A8 — 30/10/2026

Teto de 20.000 eventos por run, com última vaga terminal. Excesso não terminal retorna 429 resource_limit e encerra com failed/event_limit, preservando efeitos anteriores.
11 testes dirigidos aprovados em SQLite em 78,36 s. [Relatório A8](../04-operacoes/validacao-a8.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A9 — 30/10/2026

Cinco admissões SSE por operador, persistidas na migração 0008. TTL 30 s, renovação autorizada e limpeza no ciclo ASGI.
14 testes dirigidos aprovados em SQLite em 133,11 s, incluindo disputa entre subprocessos. [Relatório A9](../04-operacoes/validacao-a9.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A10 — 30/10/2026

available preserva configuração habilitada. enabled, worker_recent, last_seen_at, model e configuration_known explicitam presença de 60 s e desconhecimento do modelo remoto. Portal atualizado.
13 testes dirigidos aprovados em SQLite em 67,77 s. [Relatório A10](../04-operacoes/validacao-a10.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A11 — 30/10/2026

Health preserva SELECT 1 real e 200/503, sem afirmar saúde de worker/LLM.
5 testes dirigidos aprovados em SQLite em 55,42 s. [Relatório A11](../04-operacoes/validacao-a11.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A12 — 30/10/2026

Listagem valida Process e identidade da linha concedida; corrupção acessível retorna 500 invalid_response, sem expor dados ou lista parcial. Vazio autorizado mantém 200.
9 testes dirigidos aprovados em SQLite em 26,76 s. [Relatório A12](../04-operacoes/validacao-a12.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Registro de execução A13 — 30/10/2026

Seis rotas verificadas individualmente. Quota física de 1.000 admissões por run antes do corpo/efeito, com recusas auditadas e validação comum de executor.
32 testes dirigidos aprovados em SQLite em 62,67 s. [Relatório A13](../04-operacoes/validacao-a13.md).
Suíte completa reservada ao fechamento A; PostgreSQL pendente.

## Fechamento local A — 30/10/2026

A0–A13 verificados no escopo local, com aceites dirigidos preservados. Após A13, scripts.dev check passou com 390 testes SQLite em 1.328,12 s; comando completo em 1.336,15 s.
Lint/formato de 212 arquivos, links/invariantes, OpenAPI e whitespace aprovados.
[Relatório completo, matriz, workflow e limites](../04-operacoes/validacao-a-fechamento.md).
PostgreSQL, runtimes/LLMs reais e revisão manual continuam pendentes. Bloco I não iniciado; nenhuma publicação autorizada por este fechamento.

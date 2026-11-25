# Auditoria de Backend & Tools — 28/10/2026

## Parecer executivo

As seis ferramentas e a API de conversas/execuções estão implementadas localmente, com autenticação técnica, concessões por processo/corpus, reserva de worker, persistência transacional, memória e SSE retomável. A demonstração confirmou as seis tools, os dois recibos de escrita, seus hashes e replay idempotente. Isso comprova o protocolo com dados sintéticos; não comprova conexão com Hermes, LangGraph ou uma LLM real.

**Há impedimentos para tratar esta versão como segura para exposição compartilhada ou como benchmark auditável concluído.** Foram encontrados avisos críticos na versão do Next.js, avisos em dependências Python, desvio reproduzível do orçamento das tools e aceitação de registros experimentais sem correspondência nas chamadas reais. O participante sem login continua válido somente dentro dos limites do piloto local.

Nesta auditoria foi reforçada a tipagem das fronteiras HTTP e dos modelos compartilhados. Os demais achados permanecem abertos. A verificação completa passou com **82 testes**, Ruff, formato e validação de links/invariantes; aprovação funcional não elimina problemas de segurança demonstrados por sondas e scanners.

## 1. Escopo, base e método

- Worktree examinada/alterada: `C:\Users\roger\.codex\worktrees\backend-tools\benchmark-ciia-hermes`; branch `team/backend`.
- HEAD na abertura: `5f28cf2`. Havia alterações locais e arquivos novos de v0.3 antes desta tarefa; foram preservados. O relatório considera esse trabalho não commitado, sem atribuí-lo a esta auditoria.
- A referência local `origin/main`, `4987721`, já era ancestral de HEAD: `git rev-list --left-right --count HEAD...origin/main` retornou `4 0`. Não houve fetch; isso não certifica atualização do remoto em 28/10. Não foi realizado merge sobre a árvore com trabalho local.
- `D:\benchmark-ciia-hermes` não foi usado como fonte do estado atual nem recebeu correções copiadas.
- Leituras: AGENTS da worktree, arquitetura, PRD, TDD, guia Backend, contratos, fluxo Git, índice de ADRs, runbooks, API, plano de lacunas e evidências anteriores. Revisão de contratos, serviços, clientes, worker, persistência, migrações, exportação, proxy do chat, containers e CI.
- Método: análise estática manual, testes, demos sintéticas, diagnóstico em SQLite temporário e consulta atual de avisos de dependências. Orientação: skills `security-best-practices` e `coding-guidelines`.
- Não é pentest de implantação ou certificação de segurança. Não foram usados documentos reais nem enviados ataques a servidor compartilhado.

As referências de código usam linhas do estado local desta auditoria; mudanças posteriores podem deslocá-las.

## 2. Implementado versus pendente

| Área | Estado local verificado | Pendência/limite |
| --- | --- | --- |
| Seis tools | Rotas fixas, catálogo fechado, contexto conferido no servidor | Homologar consumidores reais |
| Processo/inventário | Metadados, cobertura e inventário | Qualidade/completude dependem de Documentos |
| Busca | Substring literal, escopo antes do limite, escape de `%`/`_`, ordem determinística | Sem ranking/embeddings/filtros de domínio; diferença Unicode entre bancos |
| Leitura | Documento ou páginas positivas/únicas no corpus autorizado | Sem prova de leitura humana ou interpretação pelo modelo |
| Checklist | Importação administrativa versionada e imutável | Homologação metodológica e identificação por procedimento |
| Escritas | Evidência resolvida no servidor, requisito válido, transação, idempotência, hash e recibo relido | Validade semântica da evidência exige revisão independente |
| Autenticação | Bearer técnico de operador/worker e hash no banco | Sem login individual, expiração/rotação automática ou trilha de login |
| Autorização | Dono, concessões atuais e `can_write` do dono/worker | Participantes do mesmo operador não são identidades isoladas |
| Conversas | Persistência, uma execução ativa por conversa, memória concluída | Detalhe sem paginação completa; lista limitada a 100 |
| Execuções | Fila SQL, claim, reserva, heartbeat, timeout, resultado idempotente | Sem detecção de worker conectado; fila `queued` sem expiração própria |
| Streaming | Eventos confirmados antes de transmitir, cursor/snapshot consistente | Payloads SSE não têm união validada equivalente aos corpos HTTP |
| Auditoria v0.3 | `tool_calls`, migração 0004, tentativas, duração, erros e replays | Orçamento e vínculo com declaração experimental ainda vulneráveis |
| Clientes comuns | Contexto injetado, tradução de erros, retry transitório com mesmo corpo/ID | Sucesso consumido como `dict`, sem modelo de saída por tool |
| Adaptadores reais | Protocolo e carregador de fábrica local | Hermes/LangGraph reais não implementados/homologados nesta entrega |
| Exportação | JSONL de chat, conteúdo opt-in, sem credenciais por padrão | Sem runner/exportação completos de benchmark e sem histórico integral de tentativas |
| Banco/migrações | SQLAlchemy, Alembic 0001–0004, testes SQLite | PostgreSQL, restart e restauração atuais pendentes |
| Infra | Compose em loopback, banco sem porta publicada, processos de aplicação sem root nos Dockerfiles | Imagens, TLS, identidade remota, retenção e exposição real não auditados em execução |

Fontes: [tools.py](../../services/backend/tools.py#L23), [execution.py](../../services/backend/execution.py#L39), [corpus.py](../../services/backend/corpus.py#L13), [catálogo](../../contracts/catalog.py), [adaptadores](../../agents/registry.py), [exportação](../../scripts/export_chat.py#L15).

### Catálogo das seis tools

Todas são `POST`, exigem Bearer de worker e `X-Run-Token`, e retornam HTTP 200 no sucesso. O `ToolContext` deve coincidir com a execução reservada. O modelo recebe apenas argumentos de negócio do catálogo.

| Rota | Entrada além do contexto | Saída | Limite/interpretação |
| --- | --- | --- | --- |
| `/tools/consultar_processo` | Nenhuma | `ProcessResult` | Metadados, inventário e cobertura da exportação |
| `/tools/buscar_documentos` | `query` 1–200 caracteres; `limit` inteiro 1–20 | `SearchResult` | `items: []` é sucesso da busca; não comprova ausência no processo original |
| `/tools/ler_documento` | `document_id`; `pages` opcional | `DocumentResult` | 200 comprova retorno das páginas; 404 para documento/página ausente |
| `/tools/consultar_requisitos` | Nenhuma | `RequirementsResult` | 404 quando a versão do checklist não foi importada |
| `/tools/registrar_pendencia` | `requirement_id`, chave, conteúdo, evidências e nota | `WriteReceipt` | Requisito precisa pertencer à versão; replay igual não duplica efeito |
| `/tools/salvar_minuta` | Chave, conteúdo, evidências e nota | `WriteReceipt` | Artefato/contexto/data/hash; conteúdo consultável na rota de artefato |

### Outras APIs e sucessos

São 21 operações de negócio/saúde, contando individualmente as seis tools; documentação automática não integra esse total.

| Método e rota | Perfil | Sucesso e significado |
| --- | --- | --- |
| `GET /health` | Público | 200 `HealthResponse`: API consultou banco; não testa LLM/worker |
| `GET /capabilities` | Operador | 200 `CapabilitiesResponse`: executores configurados e permissão de escrita |
| `GET /processos` | Operador | 200 `Process[]`: processos/corpora concedidos |
| `POST /conversations` | Operador | 201 `ConversationResponse`: conversa criada |
| `GET /conversations` | Operador | 200 lista própria; filtro opcional por participante |
| `GET /conversations/{id}` | Operador/dono | 200 `ConversationDetail`: mensagens e execuções |
| `POST /conversations/{id}/messages` | Operador/dono | 202 `RunResponse`: aceita/enfileirada, ainda pode falhar |
| `POST /runs` | Operador | 202 `RunResponse`: benchmark enfileirado sem memória do chat |
| `GET /runs/{id}` | Operador/dono | 200 `RunResponse`: estado, resultado, parciais, cursor e artefatos |
| `POST /runs/claim` | Worker do executor | 200 `ClaimedRun` com reserva; 204 sem tarefa elegível e sem JSON |
| `POST /runs/{id}/heartbeat` | Worker + reserva | 200 `HeartbeatResponse`: renovação |
| `POST /runs/{id}/events` | Worker + reserva | 200 `EventReceipt`: evento persistido com sequência |
| `GET /runs/{id}/events` | Operador/dono | 200 SSE; falhas posteriores usam `stream_error` |
| `POST /runs/{id}/result` | Worker + reserva | 200 `RunResponse`: resultado armazenado, inclusive `failed`/`timed_out` |
| `GET /artifacts/{id}` | Operador/dono | 200 `ArtifactResponse`: conteúdo e recibo |

`/docs`, `/redoc`, `/openapi.json` e página auxiliar do Swagger são recursos públicos do framework. Não existe endpoint de login/logout/refresh; provisionamento é administrativo. Fonte: [rotas/OpenAPI](../../services/backend/app.py#L94).

## 3. Catálogo de autenticação, respostas e estados

### Identidade e credenciais

| Elemento | Validação | Evidência que fornece |
| --- | --- | --- |
| Bearer operador | Hash corresponde ao principal, perfil e concessão do recurso | Identifica a credencial técnica, não a pessoa participante |
| Bearer worker | Perfil worker, executor no claim, concessões explícitas | Autoriza o worker técnico |
| `X-Run-Token` | Aleatório; hash comparado em tempo constante, worker/run, reserva/tempo/estado | Autoriza a reserva; replay igual de resultado também é permitido após término |
| `participant_id` | UUID e filtro dentro das conversas do operador | Pseudônimo organizacional; não impede outro participante do mesmo operador de acessar a conversa |
| `X-Tool-Call-Id` | Formato limitado, correlação das tentativas | Ainda não vincula imutavelmente ferramenta/argumentos |

Fontes: [auth.py:26](../../services/backend/auth.py#L26), [worker_run:400](../../services/backend/execution.py#L400), [tool_context:613](../../services/backend/execution.py#L613).

### Erros tratados pela aplicação

Formato: `{"code":"forbidden","message":"…","run_id":null,"retryable":false}`. `run_id` é opcional e frequentemente nulo; não presumir correlação em todo erro. HTTP descreve a operação; `code` discrimina a causa.

| HTTP | `code` | Situação | Conduta |
| --- | --- | --- | --- |
| 401 | `unauthorized` | Bearer ausente, prefixo não aceito ou token desconhecido | Corrigir credencial; não repetir indefinidamente |
| 403 | `forbidden` | Perfil errado, concessão revogada, contexto diferente, reserva inválida ou sem escrita | Corrigir autorização/reserva |
| 404 | `not_found` | Recurso ausente ou de outro dono; documento/página/checklist ausente | Conferir recurso/inventário; não inferir ausência no SEI |
| 409 | `conflict` | Run ativo na conversa, encerrado ou reserva expirada | Consultar snapshot/estado |
| 409 | `idempotency_conflict` | Chave/evento com conteúdo diferente; resultado final divergente | Preservar operação original; nova chave apenas para nova intenção |
| 409 | `version_mismatch` | Requisitos incompatíveis com processo/corpus | Conferir versões |
| 409 | `budget_exceeded` | Nova chamada lógica após orçamento configurado | Relatar limite; não contornar IDs |
| 422 | `validation_error` | Tipo/campo/parâmetro inválido, evidência/requisito/resultado inconsistente | Corrigir conforme contrato; conteúdo rejeitado não é ecoado |
| 422 | `context_limit` | Histórico/resposta excedeu limite | Nova conversa apropriada ou relatar impedimento; sem truncamento silencioso |
| 503 | `storage_unavailable` | SQLAlchemy/banco indisponível | `retryable=true`; mesmas chaves/conteúdo no retry |
| 503 | `executor_unavailable` | Executor fora de `ENABLED_EXECUTORS` | Conferir configuração/homologação; não equivale a falha de rede |
| Legado | `not_implemented` | Literal ainda permitido no contrato | Não há 501 nas seis tools atuais; remoção exige revisão de consumidores |

Corpo inválido pode receber 422 antes da autenticação. Reserva inválida recebe 403; reconhecida e expirada pode receber 409. Recurso de outro dono recebe 404 para não confirmar existência.

O cliente comum retorna `{"error": ...}` para `validation_error`, `not_found` e `idempotency_conflict`; outros erros lançam `ToolCallError`. Repete somente falha transitória/transporte, até três tentativas por chamada lógica. Timeout depois de escrita não prova que ela falhou: mesma chave/entrada permite recuperar recibo.

### Conexão, leitura e persistência

| Sinal | Significado | Não comprova |
| --- | --- | --- |
| `/health` 200 | Banco respondeu a `SELECT 1` | Worker, LLM, corpus/checklist completos |
| `available=true` | Executor habilitado em configuração | Worker observado, adaptador instalado ou inferência |
| `queued` | Run persistido esperando claim | Que existe consumidor |
| `running` / “Agente conectado” | Worker fez claim e iniciou reserva | Conexão com LLM |
| `text_delta` | Trecho confirmado no banco | Veracidade da resposta |
| `tool`, `status=ok` | Chamada retornou sucesso e foi registrada | Compreensão da fonte |
| `ler_documento` 200 | Páginas devolvidas ao chamador | Leitura humana, uso pelo modelo ou cobertura total |
| `WriteReceipt` | Efeito confirmado com hash/ID | Correção documental/jurídica ou qualidade da minuta |
| `succeeded` | Resultado aceito pelas invariantes atuais | Sucesso independente: `verified_success` continua reservado à avaliação |
| `done` | Run terminal | Sucesso; consultar `status` |
| `stream_error` | Fluxo interrompido depois do HTTP 200 | Alteração automática do resultado; recuperar snapshot |

Os formatos não são universais: 404/405 do framework podem usar `detail`; 500 inesperado/saída inválida usa resposta genérica; proxy acrescenta 403/404/413/503 com `message`, sem `code`/`retryable`. Não existe 429 implementado. O 401 não envia `WWW-Authenticate` (achado 11).

## 4. Achados de segurança e integridade

As severidades combinam impacto/exposição observados. Aviso de scanner é distinguido de exploração comprovada; exposição remota aumenta a prioridade em relação ao piloto fictício em loopback.

### Crítico

**01 — Next.js 14.2.35 com avisos críticos conhecidos.** Evidência: [package-lock.json:5530](../../portal/package-lock.json#L5530); `npm audit` retornou sete pacotes afetados, incluindo `next` com severidade crítica. Existem vários avisos por pacote, não sete CVEs independentes. **Impacto: sob as condições dos avisos, pode ocorrer execução remota de código no portal, cujo processo possui a credencial técnica do operador.** Consultados avisos oficiais de [RCE em servidor Windows](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36) e [RCE no otimizador SVG](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw). Aplicabilidade depende de plataforma/processamento/configuração; não foi executado exploit. Prioridade: inventariar exposição, atualizar para release suportada/corrigida e validar portal/proxy. A sugestão do npm envolve versão principal 16.4.3; não foi aplicada incidentalmente.

### Alto

**02 — Bundle TLS de certifi 2026.7.22 desatualizado.** Evidência: [uv.lock:90](../../uv.lock#L90) e [aviso oficial GHSA-6q48-6c7w-9gw2](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2). GHSA e PYSEC-2026-4320 são aliases do mesmo problema. Risco: interceptação TLS sob as condições do aviso em clientes que confiam nesse bundle. Atualizar deliberadamente o lock; o registro PYSEC recomenda 2026.10.19 ou posterior, e reconstruir imagens. Não desativar verificação TLS para contornar falhas.

**03 — Orçamento contornável reutilizando ID com outra operação.** Evidência: [charge_tool_call:632](../../services/backend/execution.py#L632), [attempt:28](../../services/backend/tools.py#L28). O servidor reconhece o ID já usado, sem exigir o mesmo nome/hash dos argumentos. Sonda com orçamento 1: duas `salvar_minuta`, mesmo `X-Tool-Call-Id`, chaves/conteúdos diferentes → **200/200 e dois artefatos distintos**. Não rompe concessões, mas permite operações adicionais e compromete paridade experimental. Corrigir vinculando ID à ferramenta/entrada canônica sob a trava; divergência deve conflitar. Aceite: operação distinta recusada, retry igual preservado sem duplicar artefato. `RUN_MAX_TOOL_CALLS=0`, padrão atual, mantém limite desativado e depende de decisão metodológica.

**04 — Resultado aceita chamada/artefato não comprovados.** Evidência: [finish:480](../../services/backend/execution.py#L480). Valida contexto/tarefa/executor/campos de avaliação e `persisted_artifact_ids`, mas não confronta cada `tool_calls` com o histórico servidor. Sonda: `tool_call_id="never-recorded"`, tool válida e `artifact_id="invented-artifact"` dentro do registro → **200/succeeded**. Esta rodada passou a rejeitar nomes de tool fora do catálogo, mas não resolve o vínculo semântico. Risco: declarações incorretas contaminarem avaliação. Aceite: chamada deve pertencer ao run; artefato deve existir/corresponder à operação; diferenças de duração/contagem devem ficar identificadas conforme protocolo metodológico.

### Médio

**05 — Bootstrap pode desfazer revogação local.** Evidência: [bootstrap:62](../../services/backend/auth.py#L62). Com tokens de ambiente presentes, cada início reprovisiona perfis locais com `can_write=True` e concessão demo. Sonda: revogar escrita/concessão de `local-operator`, rodar bootstrap → ambas restauradas. Limitado ao corpus fictício, mas surpreende quem usa o banco como autoridade de revogação. Definir criação apenas se ausente ou reconciliação administrativa explícita. Aceite: reinício não restaura privilégio revogado silenciosamente.

**06 — Defesa contra consumo de recursos incompleta.** Evidência: [create_run:194](../../services/backend/execution.py#L194), [add_event:443](../../services/backend/execution.py#L443), [handler:119](../../services/backend/app.py#L119), [proxy](../../portal/app/api/chat/%5B...path%5D/route.ts). Existem limites por campo/contexto/resposta/tempo, porém sem teto global de corpo na API, taxa, eventos/tentativas ou conexões SSE por principal. Eventos `status` podem crescer sem consumir o limite textual da resposta. O proxy verifica 650.000 bytes depois de `request.text()`, que já carregou o corpo. Fila sem worker acumula `queued`. Para uso compartilhado, definir limites anteriores ao carregamento e quotas coerentes de fila/eventos/streams, verificadas no gateway e em testes.

**07 — Disponibilidade indica configuração, não conexão.** Evidência: [capabilities:174](../../services/backend/app.py#L174), [check_executor:75](../../services/backend/execution.py#L75). Habilitar `hermes` produz `available=true` sem worker; sonda confirmou sem iniciar adaptador. A pergunta pode ficar enfileirada. Separar habilitação de worker observado recentemente; validar instalação/homologação e tratar fila sem consumidor. Enquanto isso, linguagem da UI/documentação deve indicar configuração, sem prometer conexão à LLM.

**08 — Identidade individual e ciclo de credenciais ausentes.** Evidência: [principals:17](../../services/backend/schema.py#L17), [proxy](../../portal/app/api/chat/%5B...path%5D/route.ts), [PRD](../02-arquitetura/backend-prd.md). Tokens técnicos sem expiração automática; não há login individual, sessão revogável, rotação com janela, MFA ou isolamento por participante. Desenho explícito, limitado ao piloto local fictício; não atende uso remoto multiusuário. Infra/Backend precisam definir identidade, escopo, ciclo e auditoria antes de ampliar uso. SHA-256 de token aleatório não equivale a armazenamento de senha humana; não substituir por senha fraca.

**09 — OpenTelemetry API 1.45.0 com aviso de disponibilidade.** Evidência: [uv.lock:240](../../uv.lock#L240) e [GHSA-xcq7-p3pf-p88h](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h). Scanner aponta parsing custoso de `tracestate`; correção informada em 1.45.1. Não foi localizada instrumentação ASGI OpenTelemetry explícita na aplicação; exploração por esse caminho não foi comprovada. Atualizar dependência e conferir instrumentação na implantação; presença do pacote não prova exposição.

### Baixo / manutenção

**10 — Erros e cache sem uniformidade.** Evidência: [handlers:115](../../services/backend/app.py#L115), [SSE:340](../../services/backend/app.py#L340), proxy. Erros de domínio são legíveis/seguros, mas 404/405 do framework, 500 e recusas do proxy têm formatos diferentes. `GET /runs/{id}` direto não envia `Cache-Control: no-store`, confirmado pela sonda; portal/SSE já previnem armazenamento. Padronizar consumidores, metadados sem eco de entrada e política de cache autenticado. Não foi demonstrado vazamento por cache.

**11 — HTTP 401 sem desafio Bearer.** Evidência: [tool_failure:115](../../services/backend/app.py#L115) e sonda `www_authenticate=null`. Acrescentar `WWW-Authenticate: Bearer` no 401 para interoperabilidade, mantendo 403 para recusa de autorização. Referência: [RFC 9110, 15.5.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2). Não é bypass de autenticação.

**12 — Tipagem parcial em consumidores/serviços internos.** Evidência: [tool_outcome:36](../../agents/interface.py#L36), [api do chat:60](../../portal/app/chat/page.tsx#L60), [execuções](../../services/backend/execution.py). Fronteira HTTP reforçada nesta rodada; muitos métodos internos continuam sem anotações e clientes aceitam JSON como `dict`/`any` implícito de `response.json()`. TypeScript `strict` e `Promise<T>` não validam JSON em execução. Não há mypy/pyright no check Python. Próximo passo: retornos por tool no cliente, SSE discriminado, validação/geração coerente no portal e verificador estático incremental; não instalar ferramenta fora do lock.

**13 — Documentação/evidências históricas precisam de reconciliação.** [GEMINI.md:55](../../GEMINI.md#L55) ainda descreve `AgentAdapter.run`, API sem autenticação, ausência de migrações e escritas futuras/501: superado. O [plano de 25/10](../02-arquitetura/backend-plano-lacunas.md) descreve rastreio como ausente, mas há implementação local não commitada/testada. O [TDD](../02-arquitetura/backend-tdd.md) não incorpora todo o inventário da migração 0004. O [wrapper de restore](../../scripts/database_backup.py) verifica contagens de parte das tabelas e não inclui `tool_calls`; dump completo não equivale a validação completa. Preservar históricos datados e conciliar instruções operacionais em revisão conjunta.

## 5. Dependências: resultados detalhados

| Pacote | Versão afetada fixada | Resultado |
| --- | --- | --- |
| certifi | 2026.7.22 | GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320: um problema, dois registros |
| opentelemetry-api | 1.45.0 | GHSA-xcq7-p3pf-p88h / CVE-2026-114603 |
| next | 14.2.35 | Crítico, múltiplos avisos com condições distintas |
| @next/eslint-plugin-next | 14.2.35 | Alto, propagado por glob |
| eslint-config-next | 14.2.35 | Alto, propagado pelo plugin |
| glob | 10.3.10 | Alto: CLI com comando e entrada não confiável; exploração na aplicação não localizada |
| postcss interno ao Next | 8.4.31 | Alto, processamento CSS/source maps; depende do caminho executado |
| @tailwindcss/typography | 0.5.20 | Moderado, propagado pelo parser |
| postcss-selector-parser | 6.0.10 / 6.1.4 | Moderado, complexidade no parsing |

`uv audit`: 33 pacotes, três registros, **dois problemas distintos**, nenhum adverse status. `npm audit`: sete pacotes afetados, um crítico, quatro altos, dois moderados; inclui dependências de build/desenvolvimento. Ambos retornaram código 1 por avisos, não por falha de testes funcionais.

Respostas completas em `data/audit-backend-2026-10-28/python.json` e `portal.json`, ignoradas pelo Git. Consultas podem produzir resultados novos com a evolução das bases de avisos. Nenhum lock foi alterado e não se aplicou `audit fix`. Referências complementares: [OWASP REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) e [Pydantic Strict Mode](https://docs.pydantic.dev/latest/concepts/strict_mode/).

## 6. Tipagem forte entregue nesta rodada

- Inteiros/booleanos estritos: rejeita `"2"`, `2.0` e `true` quando o campo exige inteiro. Inclui limite de busca, páginas, repetições, contadores, replay e permissões.
- Métricas/timestamps tipados; números não finitos recusados. Tokens/custo opcionais continuam `null` quando indisponíveis.
- `RunContext`, `HistoryMessage` e `TaskMetadata`: chaves obrigatórias conhecidas e extras proibidos. Histórico admite apenas papéis `user`/`assistant`; metadados definem split e repetição.
- Objetos continuam dicionários Python/objetos JSON; adaptadores válidos preservam sua indexação. UUID/datetime mantêm a representação JSON habitual.
- `/health` usa `HealthResponse` validado, substituindo schema manual.
- `ToolName` limita nomes nos registros declarados; `ErrorCode` compartilha vocabulário. Perfil autenticado/funções de autorização anotados; `fail` retorna `NoReturn`.
- OpenAPI regenerado; teste de correspondência mantido. Fixtures sintéticas incompletas de polling/retry completadas, sem afrouxar contratos reais.
- Novas regressões: coerção de tipos, números não finitos, nome de tool desconhecido, estruturas aninhadas, credenciais, revogação e saída HTTP com contexto incompleto.

Arquivos principais: [models.py](../../contracts/models.py), [execution.py dos contratos](../../contracts/execution.py), [auth.py](../../services/backend/auth.py), [errors.py](../../services/backend/errors.py), [app.py](../../services/backend/app.py), [test_contract_security.py](../../tests/backend/test_contract_security.py).

**Compatibilidade:** clientes que enviavam números como strings/booleanos ou montavam `ClaimedRun` incompleto passam a falhar. É endurecimento de validação, apesar de manter o JSON válido. Documentos, Hermes, LangGraph e Metodologia precisam revisar o pacote antes da integração compartilhada. Não foi prometida tipagem estática integral do repositório.

## 7. Portabilidade, legibilidade e observabilidade

**Portabilidade:** comandos Python usam módulos, `pathlib`, argumentos de `subprocess` e lock; esta rodada executou em Windows/Python 3.12.10. SQLite usa `BEGIN IMMEDIATE`; PostgreSQL usa locks de linha/`SKIP LOCKED`: garantias de concorrência diferentes. CI declara Linux/PostgreSQL 17, mas YAML não comprova check remoto aprovado. Busca Unicode e concorrência precisam de validação no banco final. Dockerfiles usam Linux; `sh` do backup roda dentro do container. Não houve teste atual em Linux/macOS nem build de imagens. Proxy aceita hosts de loopback por limite intencional do piloto, não como suporte a uso remoto.

**Legibilidade:** contratos e tools separados do transporte; mensagens curtas sem eco de entradas/SQL; status/códigos estáveis e recibos verificáveis. O serviço de execução concentra fila/memória/eventos/autorização/artefatos em cerca de 800 linhas, com muitos dicionários sem anotações: custo de manutenção pede refinamento incremental, sem refatoração ampla aqui. Erros domínio/framework/proxy e disponibilidade/conexão têm semânticas diferentes que precisam permanecer explícitas. O chat já traduz estados conhecidos de falha.

**Observabilidade:** tentativas registram run/chamada/tool, duração, HTTP, código, replay e hash de argumentos, sem argumentos em claro nessa tabela. Mensagens/eventos/artefatos guardam conteúdo intencionalmente no banco; exigem acesso controlado e retenção. Não há expurgo técnico, trilha completa de autenticação/administração ou coletor operacional comprovado. Exportação de chat seleciona eventos `tool` e descarta campos como `tool_call_id`, `code`, `replayed`; não cobre tentativas posteriores ao término que não geram SSE. Avaliação deve conferir o histórico servidor, não só stream/declaração do agente.

## 8. Verificações e reprodução

Comandos na worktree oficial; banco sintético SQLite nos testes/demos desta rodada.

| Comando/checagem | Resultado |
| --- | --- |
| `git status --short --branch` | `team/backend`, trabalho anterior preservado |
| `uv run --locked python -m scripts.dev test-backend` antes das mudanças | 50 aprovados; aviso Starlette/HTTPX |
| `uv run --locked python -m scripts.dev check` após mudanças | Ruff, formato, links/invariantes e **82 testes aprovados** em 226,73 s; um aviso de depreciação |
| `uv run --locked python -m scripts.dev demo` | Aprovado; zero chunks novos na reingestão |
| `uv run --locked python -m scripts.tools_demo` | Seis tools, dois artefatos com hash/replay; `real_agent=false` |
| `uv run --locked python -m scripts.audit_backend` | Diagnóstico concluído; reproduz achados 03/04/05/07/10/11 |
| `uv audit --locked --output-format json` | Código 1: três registros/dois problemas distintos |
| `npm audit --json --ignore-scripts` no portal | Código 1: sete pacotes afetados |
| `docker ps` | Indisponível: serviço Docker Linux parado |

Testes dirigidos intermediários revelaram duas fixtures de polling incompletas; foram completadas com contexto/metadados reais. Checks intermediários de importação/formato foram corrigidos. Esses resultados não foram tratados como sucesso final.

Diagnóstico reproduzível: [scripts/audit_backend.py](../../scripts/audit_backend.py). Usa apenas SQLite temporário, tokens fictícios e corpus de exemplo; não inicia worker nem chama LLM. Saída zero significa diagnóstico executado, **não aceite de segurança**. Observado:

```json
{
  "missing_auth_http": 401,
  "www_authenticate": null,
  "budget_one_two_different_writes": {
    "statuses": [200, 200], "distinct_artifacts": 2
  },
  "unverified_tool_record_result_http": 200,
  "run_cache_control": null,
  "configured_hermes_without_worker": true,
  "health": {"status": "ok", "contract_version": "0.3"},
  "bootstrap_restores_local_write_and_grant": true
}
```

**Não realizadas:** PostgreSQL 17/restart/backup/restauração com 0004 (Docker parado); jornada visual/build/lint do portal (código do portal não alterado, revisão focada em proxy/contratos/dependências); inferência e homologação de adaptadores reais (não fornecidos); teste de carga/DoS, exploração de CVEs, scan de imagens, ACLs de arquivos privados, TLS/proxy implantado, checks remotos e auditoria integral do histórico de segredos. O [registro de 24/10](validacao-backend-2026-10-24.md), com 42 testes/schema anterior, é evidência histórica, não aceite automático do estado atual.

## 9. Prioridades e responsáveis

| Prioridade | Entrega | Responsáveis/revisores | Aceite mínimo |
| --- | --- | --- | --- |
| P0 antes de exposição compartilhada | Atualizar dependências afetadas e validar condições dos avisos | Portal/Infra + Backend | Auditorias repetidas, exceções justificadas e jornada na versão corrigida |
| P0 antes de benchmark comparativo | Vincular chamada ao corpo/tool e validar registro contra servidor | Backend + agentes + Metodologia | Sondas 03/04 recusam operação/declaração inválida; retry legítimo preservado |
| P1 | Preservar revogação e definir ciclo de credenciais | Backend + Infra | Testes de reinício/rotação/revogação |
| P1 | Worker observado; limites de fila/corpos/eventos/SSE | Backend + Infra + Metodologia | Falta de consumidor e excesso têm comportamento/códigos definidos |
| P1 | Homologar adaptadores/checklists | Agentes + Documentos + Metodologia | Leitura, escrita, ausência de informação, falha/recuperação pela mesma API |
| P1 | Validar PostgreSQL/0004 e restauração de todas as tabelas/hashes | Backend + Infra | Evidência nova em banco isolado |
| P2 | Runner/exportação de benchmark e tentativas completas | Backend + Metodologia | Manifesto, repetições e JSONL conferidos |
| P2 | Erros/cache/desafio 401 e tipos dos consumidores | Backend + Portal + agentes | Compatibilidade e regressões por resposta/erro/SSE |
| P2 | Conciliar instruções operacionais | Backend + equipes afetadas | Nenhum guia vigente descreve API sem auth, `run` legado ou tools 501 |

Estado: implementação local reproduzível com contratos reforçados, **ainda com achados e integrações pendentes**. Não houve commit, push, PR, implantação ou promoção para production.

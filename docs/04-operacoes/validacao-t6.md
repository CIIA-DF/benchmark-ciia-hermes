# T6 — salvar_minuta

Data: 29/10/2026. Escopo: somente T6 do [plano](../02-arquitetura/backend-plano-lacunas.md), na worktree oficial team/backend. Trabalho local; liberação manual e homologação não se confundem com implementação. Sem revisão automática/Astra, commit, merge, push, PR ou deploy.

## Objetivo e mudança entregue

Fechar o aceite específico de salvar_minuta, reutilizando a escrita e os contratos reforçados em T0/T5. O escritor já confere fonte, payload canônico, chaves, hashes, contexto e recibo antes do commit, no replay e na leitura independente posterior. Não foi criado ou alterado outro escritor no T6.

A lacuna encontrada era no consumidor: tool_outcome validava WriteReceipt, mas salvar_minuta ainda não participava da conferência do contexto da execução nem do hash do conteúdo enviado. Um 200 estruturalmente válido de outro contexto ou com hash falso podia ser aceito pelo cliente.

Implementação de produção restrita a [agents/interface.py](../../agents/interface.py): incluir salvar_minuta na conferência de contexto e aplicar a ambas as escritas a mesma verificação de content_sha256. O modelo da entrada é obtido por TOOLS[name].input_model, preservando PendencyInput e WriteInput sem ramos duplicados. Não há alteração de servidor, schema JSON, dependência, migração, código de erro ou rota nesta rodada. Contratos, referência da API, plano e runbook documentam o comportamento.

Resposta válida mantém o JSON. Sucesso com contexto/hash incompatível passa a ToolCallError definitivo, sem retry automático nem eco do corpo rejeitado. A mudança afeta clientes síncrono/assíncrono; a checagem de pendência continua pelo mesmo catálogo e é revalidada na suíte. Consumidores próprios que não usam esses clientes precisam conferir contexto, hash e erro de forma equivalente. Backend, Documentos, Hermes/LangGraph e Metodologia devem revisar compatibilidade antes da integração compartilhada; a revisão Astra permanece manual com o responsável.

## Entrada, saída e componentes comuns

WriteInput mantém run_id UUID, process_id, corpus_version, requirements_version, idempotency_key, content, evidence não vazia e evidence_note. Campos extras são proibidos; requirement_id não faz parte da entrada de minuta. Conteúdo/nota seguem Text (1–100.000 caracteres após normalização); referências de chunk usam documento/chunk/página positiva e inteira estrita, ou inventário tipado com processo/corpus.

WriteReceipt mantém contexto, artifact_id UUID, persisted_at com fuso, content_sha256 e replayed booleano estrito. Essa tipagem vem do T5 e não foi modificada. Hash de conteúdo refere-se aos bytes UTF-8 do content validado; input_sha256 persistido refere-se à entrada completa canônica. Nenhum deles comprova qualidade da redação, arquivo original ou sustentação semântica das fontes.

| Elemento comum | Origem e uso em T6 |
| --- | --- |
| Catálogo de entrada/saída | T0: cliente e servidor usam TOOLS; T6 reutiliza o modelo para conferir o hash |
| Contexto, credenciais e reserva | T0: Bearer de worker, X-Run-Token e contexto do run; T6 confere também o contexto da resposta no cliente |
| Identidade e orçamento | T0-R2: reserva lógica durável antes do domínio; mesmo ID não muda corpo/tool e falha não libera orçamento |
| Escrita autorizada | T0-R1: perfis/concessões atuais do worker e proprietário, com can_write de ambos na transação do efeito |
| Fontes | T5: Chunk validado contra chave/processo/corpus/texto e página pedida; inventário confere escopo |
| Persistência e recibo | T5: escritor único, comparação de payload/recibo/hash/chaves/contexto e releitura independente |
| Novas tentativas | Cliente comum: até três tentativas transitórias com mesmo ID/corpo; T6 recusa sucesso inválido definitivamente |
| Auditoria | Tentativa, hash dos argumentos, HTTP, código, replay e artefato; limite de contagem pós-commit descrito abaixo |

## Workflow e transferências

Contexto do run reservado → busca/inventário → leitura opcional de documento/páginas → conteúdo fundamentado e referências → WriteInput com contexto injetado → reserva lógica durável → revalidação de autorização na transação → conferência de fontes → escrita/replay comum → commit de artefato/recibo/auditoria → leitura independente do registro → cliente confere contexto/hash/contrato → artifact_id para GET do operador e futura declaração experimental.

| Produtor | Dado de saída | Consumidor |
| --- | --- | --- |
| consultar_processo | Identidade do processo/corpus e inventário | Contexto e evidência de limitação documental |
| buscar_documentos | document_id/chunk_id/page | Leitura opcional e evidence de WriteInput |
| ler_documento | Texto/origem/página | Fundamentação do conteúdo; não cria chunk_id |
| Agente | content, evidence, evidence_note, chave | salvar_minuta, sob contexto injetado pelo cliente |
| salvar_minuta | WriteReceipt: artifact_id, contexto, instante, hash, replay | Cliente/adaptador e conferência independente do operador |
| GET /artifacts/{id} | Payload e recibo autorizado ao proprietário | Conferência de conteúdo/fontes/hash; declaração experimental fica sob A7/A9 |

Checklist e registrar_pendencia não são pré-requisitos. O teste da jornada remove somente o checklist sintético do banco temporário e salva a minuta sem pendência. A ferramenta continua vinculada à requirements_version do run para consistência do contexto, mas não exige um requirement_id.

O agente escolhe as tools; o workflow representa dependências de dados, não política obrigatória de raciocínio. A validação de fontes comprova existência/coerência estrutural no corpus armazenado, sem atestar que o texto da minuta é sustentado por elas. Hash do recibo não é hash do PDF ou das evidências.

## Catálogo de respostas e recuperação

| HTTP/código | Situação | Efeito e conduta |
| --- | --- | --- |
| 200 WriteReceipt, replayed=false | Nova minuta confirmada e relida | Conferir conteúdo e recibo no artefato |
| 200 WriteReceipt, replayed=true | Mesma chave/corpo com efeito íntegro | Mesmo artefato/hash/instante, sem duplicação |
| 401 unauthorized | Credencial inválida ou ausente | Sem confirmação; não repetir automaticamente |
| 403 forbidden | Contexto, reserva, concessão ou escrita atual recusados | Sem novo efeito; revogação dos dois perfis efetiva |
| 404 not_found | Processo/corpus autorizado ausente no domínio | Falha depois da reserva lógica, sem liberar ID/orçamento |
| 409 conflict/version_mismatch/budget_exceeded/idempotency_conflict | Estado, versão, orçamento ou identidade/chave incompatíveis | Não trocar IDs para contornar a recusa |
| 422 validation_error | Entrada, campo extra ou evidência inválida/ausente/estrangeira | Sem nova minuta; corrigir argumentos exige ID lógico novo |
| 500 invalid_response | Fonte, payload ou artefato/recibo armazenado inconsistentes | Erro seguro e definitivo; investigação administrativa |
| 503 storage_unavailable | Falha de banco no efeito ou na confirmação | Transitório; após commit o efeito pode existir, repetir mesmos IDs/corpo |

Nenhum código foi adicionado no T6. 500 já consta na tool desde T1-R/T5. Um 200 inválido é recusado no cliente como ToolCallError, sem transformação em sucesso, eco de conteúdo ou retry automático; não se altera retroativamente o status HTTP recebido.

Mesma identidade com outra entrada/tool retorna 409 antes do efeito. Nova identidade também não pode contornar orçamento 1; retry igual recupera o recibo original. Nova identidade com mesma chave/corpo pode obter replay, consumindo seu orçamento lógico. Mesma chave com outro corpo válido retorna 409.

Antes do commit, falha desfaz artefato/recibo e sucesso transacional; auditoria de falha sobrevive em transação própria. Depois do commit, falha de releitura não desfaz a minuta. Se a reserva/run terminar, consultar como operador em vez de reabrir a execução para repetir efeitos.

## Evidências integradas

Novo [test_t6.py](../../tests/backend/test_t6.py), 21 casos no total, com conteúdo e bancos sintéticos temporários:

- Busca → leitura → minuta sem checklist ou pendência → GET independente. Confere conteúdo normalizado com acentuação, referências de chunk/inventário, hash da entrada completa, hash de conteúdo e recibo de replay.
- Cinco entradas inválidas: evidência vazia, chunk ausente/externo, página divergente, inventário estrangeiro e requirement_id extra; 422 auditado e nenhum efeito.
- Duas corrupções de chunk: null e identidade divergente; 500 seguro auditado, sem artefato.
- Orçamento 1: tentativa de mudar corpo usando mesmo ID é recusada; ID novo não obtém segundo efeito; retry original recupera o mesmo artefato e histórico esperado.
- Concorrência com IDs lógicos diferentes e mesma chave/corpo: uma escrita e um replay, um artefato; outra entrada com essa chave conflita.
- Três corrupções do artefato já persistido: contexto do recibo, UUID divergente e conteúdo do payload; replay recusado com 500 seguro, preservando o registro existente.
- Falha SQL após INSERT e antes do commit: rollback, auditoria 503 e recuperação usando a mesma identidade.
- Conteúdo reescrito entre INSERT e commit, mesmo ajustando ambos os hashes: divergência do pedido detectada e rollback completo.
- Falha de leitura independente após commit: 503 seguro, efeito existente e recuperação por replay sem duplicar.
- Quatro jornadas com clientes reais síncrono/assíncrono sobre HTTP do backend e transporte controlado: recibo adulterado em contexto ou hash é recusado sem retry, com chamada lógica marcada como erro. O artefato legítimo que precedeu a adulteração permanece armazenado.
- Validador compartilhado recusa os quatro campos de contexto divergentes, UUID inválido, data sem fuso e hash falso; JSON válido preservado.

Regressões dirigidas incluem [T0](../../tests/backend/test_t0.py), [T0-R1](../../tests/backend/test_t0_r1.py), [T0-R2](../../tests/backend/test_t0_r2.py) e [protocolo dos adaptadores](../../tests/integration/test_adapter_protocol.py). Cobrem também mesmo ID concorrente com entradas diferentes, revogação de worker/proprietário na janela reserva/efeito e perda de resposta após commit nos dois clientes. Doubles de transporte e adaptadores sintéticos não comprovam inferência real.

Comando dirigido: `uv run --locked python -m pytest tests/backend/test_t6.py tests/backend/test_t0.py tests/backend/test_t0_r1.py tests/backend/test_t0_r2.py tests/integration/test_adapter_protocol.py`. **57 aprovados** em SQLite, 188,82 s. Inclui os 21 casos novos de T6 e as regressões mencionadas. Um aviso de depreciação Starlette/HTTPX permanece. Suíte completa concluída; fechamento abaixo.

## Limitações e aceite pendente

- PostgreSQL não executado: docker ps não alcança dockerDesktopLinuxEngine (pipe ausente). SQLite não homologa concorrência, travas, falhas transacionais ou restauração no PostgreSQL. Essa verificação continua com Infra em banco isolado.
- Mantida a instrumentação do ADR 007/T5: sucesso na transação do efeito e falha de confirmação pós-commit podem gerar registros separados sob o mesmo ID lógico. O cenário produz 200/503/200 para duas requisições HTTP (falha de confirmação e retry). Não contar linhas cegamente como requisições; orçamento lógico permanece único. Fases/contagem explícitas seguem para observabilidade/A7 e revisão CTO.
- GET de artefatos foi usado para conferência de dados válidos. Integridade e erro uniforme de payload corrompido nessa API seguem para A8/A0. Não há nova tool de leitura de artefato.
- IDs/datas/hashes válidos no cliente não autenticam criptograficamente o recibo nem provam persistência por fonte independente; a conferência pelo operador complementa o retorno da tool. Conteúdo científico e homologação de agentes/checklists permanecem externos.
- Sem alteração de schema ou migração; registros já sujeitos ao endurecimento de T5 podem ser recusados se inconsistentes. Sem backfill ou reparo silencioso. Reversão de código exige manter clientes/servidor compatíveis; não implica apagar artefatos.
- Alterações anteriores, auditoria e histórico preservados. Não houve sincronização/merge nesta rodada; integração futura exige sincronização coordenada antes de PR. Dependências vulneráveis e demais achados originais continuam nos blocos próprios.

Estado: T6 implementado e verificado localmente em SQLite. Tools T0–T6 não significam aceite global da auditoria. Blocos de APIs, operação e dependências aguardam liberação; revisão Astra/CTO permanece manual.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **219 testes aprovados** em SQLite, 581,37 s. Inclui as regressões anteriores e os 21 casos novos de T6.
- Execução dirigida: **57 aprovados**, 188,82 s; todos estão incluídos na suíte completa, sem contagem adicional de cobertura.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado; nenhum schema foi alterado no T6.
- `uv run --locked python -m scripts.validate_repository`: aprovado após documentação. `git diff --check`: sem erros de whitespace. Diff T6 revisado, com escritor/servidor preservados e nenhuma alteração prévia apagada.
- Um aviso de depreciação Starlette/HTTPX permanece. PostgreSQL não executado por indisponibilidade do Docker Linux. Sem revisão automática/Astra, commit, merge, push, PR ou deploy.

T6 encerrado como implementação/verificação local. Aceite manual, PostgreSQL e homologação dos agentes reais continuam separados. A0 e demais blocos de APIs/dependências não iniciados por esta entrega; aguardam liberação específica.

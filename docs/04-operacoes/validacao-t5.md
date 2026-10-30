# T5 — registrar_pendencia

Data: 29/10/2026. Implementação local na worktree oficial team/backend. Escopo liberado pelo responsável: somente T5 do [plano](../02-arquitetura/backend-plano-lacunas.md). Nenhum commit, push, PR, deploy ou revisão automática/Astra. T6 depende de solicitação específica.

## Objetivo, achados e limites

Reforçar requisito, evidências, efeito persistido, recibo e consumidor de registrar_pendencia. A inspeção local encontrou três lacunas: requisito conferido só pela existência da chave, evidência armazenada acessada sem validação do payload e replay devolvendo recibo sem conferir sua correspondência com o artefato. O cliente validava a estrutura, mas não conferia contexto/hash do recibo de pendência contra a requisição.

As correções reaproveitam o escritor transacional único de pendências/minutas. Validação comum de evidências atende também sources do resultado final do worker. Esses consumidores foram mantidos coerentes, sem criar outro escritor ou antecipar o aceite específico T6/A7. Tipagem e integridade contribuem para os temas transversais 03/12 da auditoria; os 13 achados originais não são declarados encerrados globalmente por esta entrega.

Fora do bloco: dependências vulneráveis, identidade remota, ciclo de credenciais, infraestrutura, verificação científica, declaração experimental contra histórico, runner, adaptadores reais e tratamento uniforme de todos os erros das APIs. Permanecem nos blocos próprios. Não houve sincronização/merge de branches nesta rodada; trabalho local anterior preservado.

## Workflow e transferências

1. Operador cria run; worker autenticado recebe contexto e reserva ativa. O modelo não escolhe credenciais ou permissões.
2. consultar_requisitos fornece items[].requirement_id no processo/corpus/requirements_version. buscar_documentos fornece document_id/chunk_id/page; inventário pode fundamentar limitação documental. Não existe obrigação de chamar as consultas antes se as referências já forem conhecidas.
3. Cliente injeta contexto, Bearer e X-Run-Token. Gera X-Tool-Call-Id uma vez por chamada lógica. O agente fornece requisito, conteúdo, evidências, evidence_note e idempotency_key.
4. T0 confirma reserva lógica durável antes do domínio. A transação do efeito relê perfis/concessões atuais do worker e proprietário sob travas, confere can_write de ambos, reserva e contexto; T0-R1/R2 preservados.
5. Fontes são resolvidas no processo/corpus autorizado. O requisito selecionado é resolvido na versão autorizada; seu payload é validado e seu ID precisa coincidir com a chave consultada.
6. Chave de escrita (run_id, tool, idempotency_key) existente: validar artefato/recibo armazenados antes de decidir replay ou conflito. Mesmo corpo recupera recibo com replayed=true; outro corpo válido retorna 409 idempotency_conflict.
7. Nova escrita: gerar UUID, instante UTC e SHA-256 do conteúdo normalizado por PendencyInput; validar efeito/recibo; inserir na mesma transação; reler o registro inserido e conferir a entrada exata antes de confirmar artefato, recibo e auditoria de sucesso.
8. Após commit, conexão independente relê o registro completo e confere novamente. Cliente valida WriteReceipt, contexto da execução e content_sha256 contra o conteúdo enviado. Falha de transporte/503 permite retry limitado com os mesmos IDs/corpo; recibo inválido é falha definitiva.
9. artifact_id alimenta GET /artifacts/{id}, autorizado ao proprietário, para comparar conteúdo, requisito, referências e recibo. Hash confere os bytes UTF-8 do conteúdo validado, não o documento original nem o conjunto completo de evidências. artifact_id pode compor declaração experimental; comprovação dessa declaração contra servidor pertence ao A7.

Existência de requisito/chunk não comprova sustentação semântica, leitura/compreensão do modelo ou homologação de Metodologia. Inventário é evidência da limitação documental, não de um trecho textual específico.

## Contratos antes e depois

| Componente | Antes | Entregue em T5 |
| --- | --- | --- |
| PendencyInput | Contexto, requisito, chave, conteúdo, fontes e nota tipados | Mesmo contrato; servidor persiste a representação normalizada, sem campos novos |
| Requirement selecionado | Só existência da chave versionada | Payload Requirement completo e ID conferido; linha ausente 422, payload presente inconsistente 500 |
| Evidência de chunk | Existência da chave e acesso direto a page | Chunk validado; ID/documento/processo/corpus/texto conferidos contra a consulta; page pedida precisa coincidir |
| WriteReceipt.artifact_id | Identifier em Python | UUID em Python; JSON continua string, OpenAPI format=uuid |
| WriteReceipt.persisted_at | datetime, admitia ausência de fuso | AwareDatetime, exige fuso; JSON continua date-time |
| Recibo/efeito | Recibo novo tipado; replay usava JSON armazenado | Conferência comum de payload, recibo e chaves em geração, leitura transacional, replay e releitura independente |
| Cliente de pendência | Estrutura do resultado | Estrutura, UUID/fuso, contexto e hash do conteúdo da requisição |
| Resultado do worker | Usava a mesma validação de fontes | Inconsistência armazenada agora produz 500 seguro e rollback do resultado; resposta documentada no OpenAPI |

A conferência comum exige: tool/run/chave coerentes; payload aderente ao modelo de entrada e à sua representação canônica; input_sha256 correspondente ao payload completo; contexto de payload/recibo igual ao run; artifact_id igual à chave do registro; content_sha256 igual ao conteúdo; recibo persistido com replayed=false. Na nova escrita/releitura, o payload deve ser exatamente o pedido. No replay, primeiro se valida integridade do registro, depois se distingue outra entrada legítima (409) de registro corrompido (500).

A chave de idempotência continua diferente do ID lógico: novo ID lógico com mesma chave/corpo pode obter replay, consumindo seu orçamento; mesmo ID lógico com corpo diferente é recusado por T0 antes do efeito. Após run encerrado, consultar artefato como operador em vez de reabrir execução para repetir a escrita.

Mudanças compartilhadas alcançam salvar_minuta (escritor e WriteReceipt), GET de artefatos (schema do recibo) e resultado do worker (validação de fontes). Não se declara que esses blocos passaram por aceite específico completo. Backend, Documentos, Hermes/LangGraph e Metodologia devem revisar compatibilidade; revisão manual fica com o responsável. Clientes externos que aceitavam IDs arbitrários ou timestamps sem fuso precisam se ajustar. Dados gerados normalmente pelo backend já usam UUID e UTC.

## Catálogo de respostas de registrar_pendencia

| HTTP/código | Situação | Efeito/conduta |
| --- | --- | --- |
| 200 WriteReceipt, replayed=false | Nova escrita confirmada e relida | Comparar artefato e conteúdo pelo ID/hash |
| 200 WriteReceipt, replayed=true | Mesma chave e entrada, efeito íntegro | Mesmo artifact_id, hash e instante; não duplica |
| 401 unauthorized | Credencial técnica inválida/ausente | Não anuncia persistência nem repete automaticamente |
| 403 forbidden | Reserva/contexto/concessão/escrita atual recusados | Sem novo efeito; revogação de ambos os perfis continua efetiva |
| 404 not_found | Processo/corpus autorizado ausente na consulta de domínio | Falha auditada após reserva T0 |
| 409 conflict/version_mismatch/budget_exceeded/idempotency_conflict | Estado, versão, orçamento ou identidade/chave incompatíveis | Sem segundo efeito; não trocar IDs para contornar conflito |
| 422 validation_error | Entrada inválida, requisito ausente no escopo, referência ausente, página divergente ou inventário estrangeiro | Sem novo artefato; corrigir argumentos exige novo ID lógico |
| 500 invalid_response | Requisito/chunk/payload/recibo armazenado inconsistentes | Seguro, retryable=false; investigação administrativa, sem eco de conteúdo |
| 503 storage_unavailable | Falha de banco durante efeito ou confirmação posterior | retryable=true; após commit o efeito pode existir, repetir IDs/corpo |

500 de inconsistência antes do commit desfaz inserção e auditoria de sucesso; falha auditada em transação própria. Inconsistência em artefato previamente confirmado não apaga esse registro nem permite replay falso. Se a inconsistência/falha ocorrer na releitura após commit, o efeito já confirmado permanece; não se promete rollback de um commit anterior.

O cliente trata 200 inconsistente como ToolCallError definitivo, sem eco do corpo e sem retry automático. Um UUID válido/data válida sozinhos não provam persistência; o cliente não possui uma segunda base para autenticar o recibo, por isso o workflow inclui conferência independente pelo operador.

## Evidências integradas e comandos

Novo [test_t5.py](../../tests/backend/test_t5.py): 27 cenários, com bancos e conteúdo sintéticos temporários.

- Checklist/busca → pendência com evidências de chunk e inventário → GET independente de artefato/recibo. Compara requisito, conteúdo normalizado com acentuação, referências, SHA-256 de conteúdo e hash canônico da entrada completa.
- Cinco entradas inválidas: requisito externo, chunk ausente, página errada, inventário estrangeiro e lista vazia; sem artefato, com reserva/auditoria mantidas.
- Três corrupções do requisito selecionado e três do chunk referenciado: null, campos ausentes ou identidade/escopo divergentes; 500 seguro auditado, sem efeito.
- Duas chamadas concorrentes, IDs lógicos diferentes e mesma chave/corpo: um único artefato, uma escrita e um replay. Outra entrada com a mesma chave retorna 409.
- Falha SQL após inserção e antes do commit: rollback de efeito/recibo, 503 seguro e auditoria de falha; mesma identidade recupera a escrita após restabelecimento.
- Nove corrupções de artefato/recibo já persistido: null, contexto, hash de conteúdo, UUID diferente, timestamp sem fuso, replayed persistido, requisito do payload, espaços adicionados ao payload e hash de entrada. Replay é recusado com 500; não cria outro artefato nem apaga o existente.
- Reescrita sintética do conteúdo entre INSERT e commit, mesmo ajustando ambos os hashes, é recusada por divergência do pedido; rollback completo.
- Falha de banco na releitura independente após commit: resposta 503, um artefato existente; repetição recupera o mesmo recibo sem duplicação.
- Cliente recusa contexto estrangeiro, hash diferente, ID inválido e data sem fuso; JSON válido é preservado.
- Consumidor compartilhado de fontes: payload corrompido no resultado do worker gera erro seguro e mantém run aberto, sem publicar resultado parcial como final.

[test_t0.py](../../tests/backend/test_t0.py) ampliou a jornada de perda de resposta após commit para registrar_pendencia nos clientes síncrono e assíncrono: preserva ID/corpo, retorna mesmo artefato e registra uma chamada lógica no cliente. [test_t0_r1.py](../../tests/backend/test_t0_r1.py) cobre revogação atual do worker e proprietário entre reserva e efeito nas duas escritas. Não se substitui concorrência PostgreSQL por resultado SQLite.

Execução dirigida inicial: `uv run --locked python -m pytest tests/backend/test_t5.py tests/backend/test_t0.py tests/backend/test_t0_r1.py tests/integration/test_adapter_protocol.py`: **55 aprovados**, 138,84 s em SQLite. Essa rodada incluiu os 25 primeiros cenários T5. Após revisão final, `uv run --locked python -m pytest tests/backend/test_t5.py -k 'payload_whitespace or shared_source_validation'`: **2 aprovados**, 25 não selecionados, 12,52 s. São testes incluídos na suíte completa, não contagens adicionais à sua cobertura. Um aviso de depreciação Starlette/HTTPX permanece.

Suíte completa concluída; resultados de fechamento abaixo.

## Limitações, portabilidade e revisão manual

- PostgreSQL não executado: docker ps não alcança dockerDesktopLinuxEngine, com pipe ausente. SQLite e os hooks sintéticos não homologam travas, falhas/transações ou triggers em PostgreSQL. Execução futura: TEST_DATABASE_URL apontando para banco PostgreSQL isolado, com schema/migrações revisados pela Infra.
- Sem migração, dependência ou nova rota. Dados antigos com ID não UUID/data sem fuso ou payload não canônico podem ser recusados; não houve backfill, alteração de banco real nem reparo silencioso. Correção administrativa deve respeitar imutabilidade/versionamento e preservar evidências.
- Mantida a instrumentação transacional do ADR 007: sucesso é registrado na transação do efeito. Se apenas a releitura posterior falhar, registra-se também a falha da confirmação. O cenário reproduz 200/503/200 sob o mesmo ID lógico para duas requisições HTTP (falha pós-commit e retry). Logo, linhas do histórico não equivalem sempre a requisições HTTP; orçamento lógico continua único. A distinção explícita de fases/contagem deve ser analisada no bloco de observabilidade/A7 e na revisão CTO. Não foi alterado o protocolo global de auditoria em T5.
- GET de artefato foi usado para conferência de dados válidos. Tratamento uniforme de payload corrompido/erros inesperados nessa API permanece no bloco de APIs; esta entrega garante erro seguro na tool de escrita/replay para os casos documentados.
- Não se comprovam arquivo original, sustentação semântica, compreensão do modelo, autenticidade criptográfica independente do recibo ou homologação real Hermes/LangGraph. Permanecem responsabilidades externas e blocos de aceite próprios.
- Alterações prévias e histórico documental preservados. Sem merge/sincronização, publicação ou revisão automática. Para integrar, revisar contratos e sincronizar a branch de forma coordenada antes do PR; não reescrever histórico.

Recuperação de falha transitória: manter run/ID lógico/chave/corpo; se o run terminou, usar GET de artefato como operador. Em inconsistência, inspecionar e preservar evidências do armazenamento em ambiente isolado; não forçar replay nem trocar identidade para contornar. Reversão de código não exige downgrade de schema, mas exige compatibilidade entre servidor/clientes e avaliação dos registros recusados.

Estado: T5 implementado e verificado localmente em SQLite. Liberação manual, PostgreSQL e revisão CTO separados. T6 não iniciado como bloco.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato (141 arquivos), links/invariantes e **198 testes aprovados** em SQLite, 616,34 s. Inclui todas as regressões anteriores, 27 cenários novos em test_t5.py e 2 ampliações de perda de resposta em test_t0.py.
- Dirigida inicial: 55 aprovados (138,84 s); dois cenários finais adicionais: 2 aprovados (12,52 s). Todos estão incluídos na suíte completa; não somar essas execuções como cobertura distinta adicional.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado; schema UUID do recibo e 500 no resultado do worker coerentes com aplicação.
- `uv run --locked python -m scripts.validate_repository`: aprovado após atualização documental. `git diff --check`: sem erros de whitespace. Trechos T5 e impactos compartilhados revisados; nenhuma alteração prévia apagada.
- Um aviso de depreciação Starlette/HTTPX permanece. PostgreSQL não executado por indisponibilidade do Docker Linux. Sem revisão automática/Astra, commit, merge, push, PR ou deploy.

T5 encerrado como implementação/verificação local, com as limitações acima explícitas. Liberação manual e homologação PostgreSQL permanecem pendentes. T6 não iniciado como bloco.

# T1 — consultar_processo

Data: 28/10/2026. Worktree oficial team/backend. Estado: implementado e verificado localmente em SQLite. Revisão do responsável pendente.

## Escopo e comportamento

Somente T1 do [plano](../02-arquitetura/backend-plano-lacunas.md). Sem novos filtros, metadados, ranking, ferramentas ou migrações. Alterações locais anteriores e relatório de auditoria preservados.

ProcessResult agora exige que process_id, corpus_version e requirements_version do processo coincidam com o envelope ToolContext. O inventário rejeita document_id duplicado. A leitura administrativa do inventário valida cada Document persistido e confere documento/processo/corpus do payload contra as chaves da linha selecionada. Assim, um payload corrompido não transforma uma consulta autorizada em retorno de metadados de outro escopo.

O cliente síncrono e o assíncrono usam o modelo compartilhado do T0. Para consultar_processo, também confrontam o contexto devolvido com o contexto autenticado da chamada: resposta internamente coerente de outro run/processo/corpus/requisitos é recusada com ToolCallError definitivo. Não é feito retry automático de resposta inválida, nem eco do payload rejeitado.

## Workflow de entrada e saída

1. Worker chama consultar_processo com o contexto reservado; cliente injeta contexto e cabeçalhos técnicos.
2. Backend verifica credencial, reserva, concessões e identidade lógica do T0.
3. Consulta processo/corpus e compara requirements_version; lê somente documentos desse processo/corpus, em ordem por document_id.
4. Valida os documentos armazenados, processo do envelope e unicidade do inventário antes de registrar sucesso.
5. Confirma a tentativa; cliente valida a resposta e seu vínculo com a requisição.
6. inventory[].document_id pode alimentar ler_documento. pages é quantidade, não lista de números nem prova de numeração contínua. sha256 é o hash registrado do documento completo, sem recomputação do arquivo original nesta consulta.
7. export_completeness e export_note permanecem explícitos. Inventário pode ser vazio; lista vazia/exportação parcial não prova ausência no processo SEI original. Fonte válida não prova interpretação pelo agente.

## Catálogo de respostas

| HTTP/código | Significado |
| --- | --- |
| 200 ProcessResult | Contexto, processo e inventário validados; cobertura e nota preservadas |
| 401 unauthorized | Credencial ausente/inválida |
| 403 forbidden | Contexto da chamada difere do run ou concessão/reserva não autoriza operação |
| 404 not_found | Processo/corpus autorizado não localizado |
| 409 version_mismatch | Contexto autenticado coincide com run, mas catálogo informa outra versão dos requisitos |
| 409 demais códigos T0 | Estado, identidade da chamada, idempotência ou orçamento incompatível |
| 422 validation_error | Entrada inválida |
| 500 invalid_response | Processo/inventário armazenado ou resposta produzida inconsistente; mensagem segura, retryable=false |
| 503 storage_unavailable | Falha SQLAlchemy, retryable=true; preservar corpo/ID ao repetir |

invalid_response foi acrescentado ao vocabulário compartilhado e ao OpenAPI de consultar_processo. Clientes comuns tratam como falha definitiva, sem apresentá-lo como erro corrigível de argumentos pelo modelo. A padronização global de 500/erros do proxy continua pertencendo a A0. Formato JSON de sucesso válido permanece igual; validação ficou mais restritiva. Revisão contratual de Backend, Documentos e equipes de agentes permanece necessária antes de integração.

## Evidências

21 cenários dirigidos de T1 e protocolo dos consumidores aprovados (59,27 s): divergência do processo aninhado, envelope estrangeiro, inventário duplicado, payload de documento com ID/processo/corpus trocado, cobertura complete/partial/unknown, nota preservada, contexto alterado (403), versão de catálogo incompatível (409) e falha de banco segura (503). Inventário inválido não gera tentativa com HTTP 200; o erro é auditado pelo T0.

O double de retry do cliente foi corrigido para devolver o mesmo contexto de sua execução, em vez de gerar um run_id aleatório para a resposta. Nenhuma verificação foi removida para aceitar inconsistência.

Resultados da suíte completa e revisão final registrados abaixo ao concluir. Não houve acionamento do Astra, commit, push, PR ou deploy. T2 não iniciado.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **112 testes aprovados** em SQLite (300,37 s); um aviso de depreciação Starlette/HTTPX mantido.
- `uv run --locked python -m pytest tests/backend/test_t1.py tests/integration/test_adapter_protocol.py`: 21 aprovados (59,27 s).
- `uv run --locked python -m scripts.export_openapi --check`: cópia coerente com aplicação.
- `uv run --locked python -m scripts.validate_repository`: links/invariantes aprovados após documentação.
- `git diff --check`: sem erros de whitespace; diff revisado considerando o trabalho anterior não commitado.
- PostgreSQL 17/restart não executados: Docker Linux continua parado. Não houve migração nova no T1.
- Revisão CTO/Astra e homologação de agentes reais não executadas; permanecem sob condução manual do responsável. T2 depende de nova liberação.


## Correção posterior T1-R

A revisão dirigida encontrou campo ausente do processo escapando antes da validação/auditoria. A fronteira foi corrigida posteriormente: ver [registro T1-R](validacao-t1-r.md), inclusive distinção de linha ausente e payload null. Números anteriores são históricos; aceite manual/PostgreSQL permanece separado.

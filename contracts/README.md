# Contratos v0.1 — proposta revisável

Fonte executável: [models.py](models.py). Modelos Pydantic rejeitam campos extras, IDs inválidos, páginas repetidas e offsets inconsistentes. A API gera OpenAPI em /openapi.json e documentação em /docs. Versão de contrato: 0.1; versão da aplicação: 0.1.0.

## Entidades

| Modelo | Campos e significado |
| --- | --- |
| Process | process_id estável, title, corpus_version, requirements_version, export_completeness (complete/partial/unknown), export_note obrigatória |
| Document | document_id, process_id, corpus_version, título, source, SHA-256 do arquivo ingerido, pages com número e texto |
| Chunk | chunk_id determinístico, process_id/document_id/corpus_version, source, page, start/end, text |
| SearchResult | run_id, processo, versões, completude, lista de chunks e aviso de limite de cobertura |
| ToolError | code, message segura, run_id quando conhecido, retryable |
| ExperimentRun | contexto, task_id/split/repetition, executor, commits/versões, modelo/endpoint, hash do prompt, parâmetros, início/latência, chamadas, tokens/custo, sucesso declarado, artefatos e sucesso verificado |

Processo/documento são identificados dentro de uma versão de corpus; não reutilizar IDs para outra origem. Em PDFs futuros, document_id deve vir de manifesto estável, sem depender do nome mutável do arquivo. A demo usa IDs fixos. Hash e offsets de JSON são demonstrativos, não extração de PDF. Chunks sempre apontam ao texto paginado validado. Documento sem página física precisa de contrato ampliado com localização equivalente antes da ingestão.

Chamadas de ferramenta exigem ToolContext: run_id UUID, process_id, corpus_version e requirements_version. O backend também persiste `ExperimentRun` em `POST /experiments`, permite releitura independente em `GET /experiments/{run_id}` e revisões sequenciais em `PUT /experiments/{run_id}`. `GET /experiments/{run_id}/revisions` retorna o histórico. Reenvio idêntico é idempotente; conflito de conteúdo ou revisão retorna 409. Registro não comprova sucesso da tarefa: `verified_success` continua a cargo de avaliação independente.

## Ferramentas

| Ferramenta | Entrada além do contexto | Saída prevista | Estado |
| --- | --- | --- | --- |
| consultar_processo | nenhuma | ProcessResult com Process | Implementada |
| buscar_documentos | query 1–200 caracteres, limit 1–20 (padrão 5) | SearchResult | Implementada, substring literal |
| ler_documento | document_id | DocumentResult com páginas completas | Implementada |
| consultar_requisitos | nenhuma | RequirementsResult com requirement_id, descrição e fonte | Contrato; HTTP 501 |
| registrar_pendencia | WriteInput | WriteReceipt | Contrato; HTTP 501 |
| salvar_minuta | WriteInput | WriteReceipt | Contrato; HTTP 501 |

Rotas: POST /tools/NOME. Resultado vazio da busca é 200 com items vazio e aviso; não prova ausência no processo original. Requirements versão demo-v1 é rótulo sintético, não checklist institucional validado.

Erros implementados: 422 validation_error; 404 not_found para processo/corpus/documento/execução; 409 version_mismatch para requisitos e idempotency_conflict para colisões de registro; 503 storage_unavailable (retryable); 501 not_implemented para operações ainda planejadas. Run_id é nulo quando entrada inválida ou falha de armazenamento impede associá-lo com segurança. `unauthorized` permanece reservado à futura autorização.

## Exemplos

Contexto da demo:

```json
{"run_id":"00000000-0000-4000-8000-000000000001","process_id":"PROC-DEMO-001","corpus_version":"synthetic-v1","requirements_version":"demo-v1"}
```

consultar_processo e consultar_requisitos recebem esse objeto. buscar_documentos acrescenta `"query":"material","limit":5`; ler_documento acrescenta `"document_id":"DOC-DEMO-001"`. Consulte a saída real com `uv run --locked python -m scripts.dev demo`.

As escritas acrescentam, por exemplo:

```json
{"idempotency_key":"task-001-pendencia-01","content":"Pendência experimental a revisar","evidence":[],"evidence_note":"Exportação parcial; ausência no processo original não confirmada."}
```

Junte os campos ao contexto. Essa chamada válida retorna hoje 501, nunca um recibo fictício. O futuro recibo conterá artifact_id, persisted_at, content_sha256 e replayed além do contexto. Erro atual típico:

```json
{"code":"not_implemented","message":"Contrato previsto; ferramenta ainda não implementada.","run_id":"00000000-0000-4000-8000-000000000001","retryable":false}
```

## Requisitos para implementar ferramentas de escrita

1. Validar autorização da execução/processo, corpus/requisitos e cada referência de evidência (documento, chunk e página).
2. Exigir evidence_note; lista vazia só é aceitável com justificativa de limitação revisada conforme tarefa. Não transformar busca vazia em certeza de ausência.
3. Usar chave única por (run_id, ferramenta, idempotency_key), armazenando hash canônico da entrada.
4. Mesma chave/mesmo conteúdo retorna recibo original com replayed=true; conteúdo diferente retorna 409 idempotency_conflict.
5. Gravar ação e recibo na mesma transação, confirmar commit e reler antes de declarar persistência. Timeout após commit é resolvido repetindo a mesma chave.
6. Tratar concorrência com constraint única, nunca apenas um teste prévio em memória.
7. Testar reenvio, concorrência, rollback, referência cruzada e inspeção por avaliador independente.

Esses itens continuam futuros para pendência e minuta. Mudanças de contrato/ferramenta exigem issue específica, revisão dos consumidores, exemplos, testes e revisão das equipes afetadas. O schema de registros usa migração aditiva versionada; nenhum resultado de execução substitui inspeção independente.

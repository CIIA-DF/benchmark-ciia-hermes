# T4 — consultar_requisitos

## Escopo e workflow

Implementação local na worktree oficial team/backend, somente T4 do [plano](../02-arquitetura/backend-plano-lacunas.md). Alterações restritas ao contrato de checklist, consulta, consumidor compartilhado, OpenAPI, testes integrados e documentação. Sem rota, dependência ou migração nova. T5 não iniciado; alterações anteriores preservadas.

Fluxo: importação administrativa de Requirement → tabela requirements no escopo process_id/corpus_version/requirements_version → contexto do run injetado pelo cliente → autorização e reserva lógica durável T0 → revalidação na transação do efeito → consulta filtrada pelas três chaves e ordenada por requirement_id → validação de cada payload e identidade persistida → RequirementsResult → auditoria da tentativa → validação de contrato/contexto no cliente → items[].requirement_id pode alimentar registrar_pendencia.requirement_id → artefato e recibo → GET /artifacts/{id} pelo operador para conferência independente.

O agente seleciona o requisito; descrição e fonte orientam a análise. A consulta não grava artefatos, não obriga uma sequência de tools e não atesta qualidade metodológica ou leitura/compreensão pelo modelo.

## Invariantes e contratos

- RequirementsResult exige items não vazio e requirement_id único. Cada Requirement mantém requirement_id, description e source obrigatórios, com os limites e tipos estritos existentes.
- O servidor filtra processo, corpus e versão antes de retornar requisitos; confere requirement_id do payload contra a chave da linha. Payload inválido, JSON null ou identidade divergente gera 500 invalid_response seguro, sem eco do conteúdo rejeitado.
- Ausência de linhas no escopo permanece 404; não é sucesso vazio nem falha de conexão. Falha SQLAlchemy continua 503 transitória pelo tratamento comum.
- Clientes síncrono e assíncrono usam tool_outcome: checklist válido precisa pertencer ao contexto completo da execução. Resposta de sucesso inválida é ToolCallError definitivo, sem retry automático.
- Importação administrativa permanece imutável: reimportar o mesmo checklist em outra ordem é permitido; alterar seu conteúdo exige nova versão. O importador não foi modificado nesta entrega.
- Items não possuem contexto próprio no JSON: a proveniência versionada é conferida pelo servidor na consulta e identidade persistida. O cliente confere o envelope; não dispõe de uma segunda fonte independente para provar conteúdo/homologação.

Mesmo JSON para respostas válidas. O OpenAPI agora explicita minItems=1; unicidade por requirement_id é validada no modelo, não por uniqueItems (que compararia objetos completos). Dados/respostas antes tolerados podem ser recusados. Sem novos códigos de erro ou campos de procedimento/homologação. Backend, Documentos, Hermes/LangGraph devem revisar o consumo; Metodologia continua responsável pelo conteúdo do checklist. A revisão manual/Astra pertence ao responsável e não foi acionada automaticamente.

## Entrada, saída e códigos

Entrada: ToolContext com run_id UUID, process_id, corpus_version e requirements_version; Bearer do worker, X-Run-Token e identidade de chamada são técnicos. Saída: RequirementsResult com o mesmo contexto e items de Requirement, ordenados por ID no servidor.

| HTTP/código | Situação e conduta |
| --- | --- |
| 200 RequirementsResult | Checklist presente, não vazio e validado no escopo |
| 401/403 | Credencial, contexto, reserva ou concessão recusados; não repetir automaticamente |
| 404 not_found | Checklist não cadastrado no escopo autorizado; erro recuperável pelo agente |
| 409 | Estado, versão do processo, identidade lógica ou orçamento incompatível, conforme T0 |
| 422 validation_error | Entrada fora do contrato; corrigir argumentos com novo ID lógico |
| 500 invalid_response | Payload/identidade/resposta inconsistentes; retryable=false, tentativa auditada |
| 503 storage_unavailable | Falha do banco; retryable=true, repetir com mesmo ID e corpo |

Contexto de requisição diferente do run é 403; versão válida do processo divergente segue o 409 compartilhado. Não se promete envelope seguro para todos os erros inesperados/framework, assunto do bloco A0.

## Evidências integradas

Novo [test_t4.py](../../tests/backend/test_t4.py), com 11 casos parametrizados no total:

- Importação sintética, ordem determinística, reimportação idêntica e rejeição de alteração; jornada checklist → pendência → leitura independente do artefato/recibo.
- Isolamento entre processo, corpus e requirements_version; requisito estrangeiro não pode produzir pendência no run atual.
- Seis corrupções: identidade divergente, descrição ausente, fonte vazia, lista, null e payload duplicado sob outra chave. Exigem 500 seguro auditado e reserva lógica mantida, sem efeito falso.
- Contexto estrangeiro 403 e checklist ausente 404.
- Falha durante a consulta SQL: 503 seguro, transitório e auditado, sem texto interno do banco.
- Cliente rejeita itens vazios, duplicados, inválidos e os quatro campos de contexto divergentes; JSON válido preservado.

Fixture da jornada: REQ-A e REQ-B, description “Synthetic requirement”, source “Synthetic checklist”, no banco temporário de testes. SHA-256 da lista ordenada por ID, JSON UTF-8 com sort_keys=True, ensure_ascii=False e separators=(',', ':'): 68a8241773c0833a0aa49102e89a13ef79acfc88cc6125b1aef4c032e95209ab. É um hash da fixture documentada, não um novo campo de API nem prova metodológica.

## Verificações e limitações

`uv run --locked python -m pytest tests/backend/test_t4.py tests/backend/test_migrations.py tests/integration/test_adapter_protocol.py`: **20 aprovados** em SQLite, 68,92 s. Um aviso de depreciação Starlette/HTTPX. Os 11 casos novos são parte desses 20, não testes adicionais. Suíte completa concluída; resultados finais abaixo. PostgreSQL não executado: docker ps não alcançou dockerDesktopLinuxEngine (pipe ausente). SQLite não comprova portabilidade PostgreSQL ou homologação dos runtimes reais. Não houve revisão CTO/Astra automática, commit, push, PR ou deploy.

Recuperação: não há mudança de schema; uma inconsistência deve ser investigada administrativamente e corrigida na origem respeitando corpus/checklist imutáveis e versionados. Não há reparo automático ou mutação de corpus real. Reserva e auditoria de falha permanecem; repetir a mesma operação usa os mesmos IDs/corpo conforme T0. Qualquer mudança de contrato/rollback deve manter servidor e clientes compatíveis.

Estado: T4 implementado e verificado localmente em SQLite. Liberação manual, PostgreSQL e homologação metodológica separados. T5 aguarda solicitação do responsável.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato (140 arquivos), links/invariantes e **169 testes aprovados** em SQLite, 466,40 s. Inclui os blocos anteriores e os 11 casos novos de T4.
- Execução dirigida: 20 aprovados, 68,92 s; estão incluídos na suíte completa.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado; minItems=1 coerente com o modelo de resposta.
- `uv run --locked python -m scripts.validate_repository`: aprovado após a documentação; `git diff --check` sem erros de whitespace. Diff dos trechos T4 revisado, preservando as alterações preexistentes da worktree.
- Um aviso de depreciação Starlette/HTTPX permanece. PostgreSQL não foi executado: Docker Linux indisponível. Não houve commit, push, PR, deploy ou revisão automática/Astra.

T4 encerrado como implementação/verificação local. Liberação manual e homologações permanecem separadas; T5 não iniciado.

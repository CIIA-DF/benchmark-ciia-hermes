# T3 — ler_documento

## Escopo e fluxo

Implementação local na worktree oficial team/backend, somente T3 do [plano](../02-arquitetura/backend-plano-lacunas.md). Sem nova rota, campo de resposta, dependência ou migração. T4 não iniciado; correções anteriores preservadas.

Fluxo: document_id do inventário ou document_id/page da busca → ReadInput com contexto injetado pelo cliente → autorização e reserva durável T0 → revalidação na transação do efeito → consulta de documento pelo processo/corpus/ID → validação do documento completo armazenado → seleção das páginas → DocumentResult coerente → tentativa confirmada → cliente valida envelope, documento e subconjunto pedido.

## Invariantes entregues

- DocumentResult exige documento do mesmo processo/corpus do envelope e páginas em ordem numérica crescente; Document já exige páginas positivas e únicas.
- CorpusRepository.read distingue linha ausente (404) de payload presente inválido, inclusive JSON null (500 invalid_response). Valida Document antes de acessar páginas e confere document_id/process_id/corpus_version contra a chave consultada.
- Documento armazenado com páginas repetidas, fora de ordem ou estrutura inválida é recusado, sem ordenação/reparo silencioso. A origem deve fornecer páginas em ordem documental crescente. Correção de corpus produtivo é administrativa e deve respeitar sua imutabilidade/versionamento; os testes alteram somente bancos sintéticos temporários.
- Sem pages ou com pages=null, retorna todas as páginas armazenadas; com pages explícito, exige existência e devolve exatamente o conjunto solicitado, mantendo a ordem documental, não a ordem dos argumentos.
- Não presume numeração contígua: exportação com páginas 1 e 7 pode ser lida por esses números; a quantidade de páginas do inventário não autoriza inferir página 2.
- O hash retornado é o SHA-256 registrado do documento completo, inclusive na seleção parcial. Não recalcula o arquivo original ou hash do subconjunto.
- ToolService confere documento solicitado e conjunto exato de páginas mesmo se o repositório devolver um objeto estruturalmente válido, porém incompatível com o pedido.
- Clientes síncrono/assíncrono usam o contrato compartilhado; ler_documento agora confere também o contexto completo da execução, o ID pedido e as páginas específicas. Resposta inválida é ToolCallError definitivo, sem eco de conteúdo nem retry automático.

O servidor conhece o documento armazenado e preserva a leitura integral quando não há filtro. O cliente valida a resposta recebida, mas não possui um segundo manifesto independente de todas as páginas; por isso não se promete prova independente de completude do documento original. Retorno de páginas não comprova compreensão pelo modelo ou leitura humana.

## Entradas, saídas e respostas

ReadInput: run_id, process_id, corpus_version, requirements_version, document_id e pages opcional (lista não vazia de inteiros estritos positivos/únicos). Cliente injeta contexto e cabeçalhos técnicos. Saída DocumentResult mantém o mesmo JSON: contexto e document com identidade, título, origem, sha256 e pages de number/text.

| HTTP/código | Situação |
| --- | --- |
| 200 DocumentResult | Documento integral ou páginas solicitadas, com contexto conferido |
| 401/403 | Credencial, contexto, concessão ou reserva não autorizada |
| 404 not_found | Documento inexistente/fora do processo autorizado ou página pedida inexistente |
| 409 | Estado, versão, identidade lógica, idempotência ou orçamento incompatível |
| 422 validation_error | Entrada inválida, como páginas vazias, repetidas, zero ou tipos coercíveis |
| 500 invalid_response | Documento/payload/resposta inconsistente; retryable=false, sem conteúdo rejeitado |
| 503 storage_unavailable | Falha do banco, retryable=true; manter IDs/corpo ao repetir |

500 invalid_response já está documentado nas tools pelo T1-R; OpenAPI conferido sem alteração de schema nesta entrega. O endurecimento de validação pode rejeitar dados/respostas anteriormente tolerados; revisão de Backend, Documentos e agentes continua necessária antes da integração compartilhada.

## Workflow para consumidores

- Inventário fornece document_id e quantidade, sem prometer todos os números de página.
- Busca fornece document_id/chunk_id/page; documento/página alimentam a leitura.
- Leitura fornece texto/origem/página para fundamentação, preservando identidade e hash registrado.
- Evidence de escrita continua usando referências de chunks da busca ou inventário autorizado. A leitura não fabrica chunk_id, não grava artefatos e não impõe sequência fixa de tools ao agente.

## Evidências integradas

Novo tests/backend/test_t3.py:

- Jornada inventário e busca → leitura; integral sem filtro; pedido com ordem inversa retorna ordem documental; hash de leitura parcial preservado.
- Sete corrupções de documento: ID, processo, corpus, páginas duplicadas, ordem invertida, páginas ausentes e JSON null. Exigem erro 500 seguro e tentativa auditada, sem sucesso falso, com reserva lógica mantida.
- Documento/página ausente 404; listas vazias, repetidas, zero, bool ou string nas páginas geram 422.
- Páginas não contíguas 1/7 funcionam; página 2 ausente retorna 404.
- Repositório devolvendo outro documento ou páginas extras é recusado pelo serviço.
- Cliente recusa envelope estrangeiro, documento diferente, página substituída, páginas extras/duplicadas/fora de ordem. Resposta válida mantém o JSON.
- SQLAlchemyError continua 503 seguro e transitório.

Execução dirigida: `uv run --locked python -m pytest tests/backend/test_t3.py tests/backend/test_tools.py tests/integration/test_adapter_protocol.py`: 25 aprovados em SQLite (81,46 s), um aviso de depreciação Starlette/HTTPX. Ajuste de binding da variável no double de teste foi feito antes da suíte completa; nenhuma verificação foi removida.

Suíte completa concluída; resultados finais abaixo. PostgreSQL permanece indisponível porque o Docker Linux está parado; não se presume equivalência a partir de SQLite. Sem revisão automática/Astra, commit, push, PR ou deploy. A liberação manual continua com o responsável.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **158 testes aprovados** em SQLite (383,00 s), incluindo correções anteriores e os 13 cenários novos de T3.
- A execução dirigida anterior teve 25 aprovados (81,46 s); são parte da cobertura da suíte, não 25 casos distintos adicionais.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado; cópia permanece coerente, sem mudança de schema JSON nesta entrega.
- `uv run --locked python -m scripts.validate_repository`: links/invariantes aprovados após documentação. Diff dirigido revisto sem erros de whitespace.
- Mantido um aviso de depreciação Starlette/HTTPX. PostgreSQL não executado: Docker Linux indisponível.
- Nenhum deploy, commit, push, PR ou revisão automática/Astra. Liberação manual e homologação PostgreSQL permanecem pendentes.

Estado: T3 implementado e verificado localmente. T4 não iniciado; demais achados da auditoria seguem no planejamento próprio.

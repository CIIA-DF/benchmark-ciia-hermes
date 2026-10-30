# F2 — buscar_documentos: rejeição explícita de U+0000

Escopo: F2 do [plano vigente](../02-arquitetura/backend-plano-blocos.md), na worktree oficial team/backend. Alterações anteriores preservadas. Sem commit, merge, push, PR, deploy ou revisão automática/Astra; F3 aguarda liberação.

## Problema e correção

SearchInput admitia U+0000 no termo de busca. A aceitação por um banco não estabelece semântica portátil para esse caractere; não se deve permitir truncamento, remoção ou transformação em consulta mais ampla. O F2 torna essa entrada explicitamente inválida antes de chegar ao SQL.

Alteração de produção restrita ao campo SearchInput.query em contracts/models.py: mantém string, min_length=1 e max_length=200 e acrescenta pattern `^[^\x00]+$`, com descrição pública de que U+0000 não é permitido. O padrão exclui o caractere em qualquer posição. Não há limpeza, substituição ou normalização Unicode nova.

OpenAPI foi regenerado. O catálogo das tools deriva o mesmo padrão do modelo, sem regra duplicada no serviço ou no repositório. A busca literal, escape de curingas, ordenação, limite e filtros por processo/corpus do T2 foram preservados. Sem dependência, migração, nova rota, cabeçalho ou código de erro.

## Workflow, atribuição e orçamento

Cliente injeta contexto do run e cabeçalhos técnicos → requisição de buscar_documentos recebe UUID físico F0 → SearchInput rejeita NUL → handler seguro de validação → identificação do run por credencial e lease → reserva lógica durável conforme T0 → auditoria da entrada recusada → tentativa física failed com 422 preparado.

Para entrada recusada, args_sha256 é o SHA-256 dos bytes do corpo recebido, conforme política existente, não do DTO inválido nem do termo limpo. O corpo/termo não aparece no erro ou histórico em claro. O teste confere esse hash contra a requisição enviada e compara reserva, histórico de compatibilidade e tentativa física. Não ocorre consulta SQL de chunks.

Com orçamento 1, NUL reserva o ID lógico quando a chamada é atribuível. Repetir exatamente a mesma entrada mantém 422 e cria outra tentativa física, sem segunda reserva. Corrigir os argumentos com o mesmo ID gera 409 idempotency_conflict; usar ID novo está sujeito ao orçamento e recebe 409 budget_exceeded quando esgotado. O F2 não redefine a política de orçamento. Recusas de identidade, estado ou orçamento seguem sua precedência existente quando a entrada é auditada, podendo produzir 409 em vez do 422 de validação.

Sem lease válido, não se atribui o run alegado pelo corpo nem se cria reserva nele. A entrada inválida permanece 422 segundo a ordem de validação existente; a tentativa física sem atribuição pode ser observada globalmente no F0. Não se usa esse retorno para comprovar autenticação ou conexão do agente.

## Contratos, consumidores e respostas

| Entrada/situação | Resultado |
| --- | --- |
| U+0000 sozinho, no início, no meio ou no fim | 422 validation_error, retryable=false; consulta não chega ao SQL de busca |
| Texto contendo os seis caracteres literais de uma sequência de escape, como barra invertida seguida de u0000 | Continua permitido; não equivale ao caractere NUL após decodificação JSON |
| Termo válido com resultado | 200 SearchResult, com escopo/limite/IDs conferidos conforme T2 |
| Busca válida vazia | 200 com lista vazia, cobertura e warning preservados |
| ID lógico com outra entrada | 409 idempotency_conflict |
| Orçamento lógico esgotado | 409 budget_exceeded |
| Resposta/índice armazenado inconsistente | 500 invalid_response seguro, conforme T2 |
| Falha real de armazenamento | 503 storage_unavailable transitório, conforme T2 |

ToolContext, SearchResult, tipos de autenticação e demais códigos continuam iguais. Um NUL não deve ser reportado como falha transitória do banco nem transformado em busca bem-sucedida. Os clientes comuns síncrono/assíncrono recebem validation_error recuperável pelo agente, sem retry automático; a nova chamada com argumentos corrigidos tem identidade lógica própria e respeita o orçamento.

Backend, Documentos e Hermes/LangGraph devem revisar o schema atualizado antes de integrar. Consumidores que validam argumentos pelo catálogo também passam a rejeitar NUL. Homologação de provedores/adaptadores reais não é presumida a partir do JSON Schema ou doubles.

## Dependências de dados

Termo válido/contexto/limit → SQL literal filtrado pelo processo/corpus antes do limite → SearchResult.items de Chunk → document_id/page podem alimentar ler_documento; document_id/chunk_id/page podem alimentar evidence de registrar_pendencia ou salvar_minuta.

NUL interrompe esse fluxo antes da recuperação; não produz resultados ou referências de evidência. Busca vazia continua sem provar ausência no processo original. Recusa HTTP não comprova leitura/compreensão do modelo. Filtros semânticos, embeddings e normalização nova permanecem fora do F2.

## Evidências integradas

Novo test_f2.py, nove cenários:

- Quatro posições do NUL: HTTP 422 seguro, sem eco do termo, guard SQL que falha se ocorrer SELECT de chunks, reserva lógica e tentativa física com hash do corpo recebido, started/failed e client_received=null.
- Orçamento 1: repetição da recusa, alteração de argumentos no mesmo ID e novo ID com orçamento esgotado; quatro UUIDs físicos e uma reserva lógica.
- Lease inválido: nenhuma atribuição/reserva no run alegado pela entrada.
- OpenAPI e catálogo expõem o mesmo padrão; sequência literal de escape continua permitida e recebe 200 vazio no corpus sintético.
- Clientes síncrono e assíncrono sobre HTTP do backend com transporte controlado: validation_error seguro, uma requisição e chamada lógica marcada como erro, sem retry.

Regressões T2 exercitam caracteres %, _, barra, Unicode com/sem acentos, busca vazia, escopo antes do limite, ordenação, corrupção, cliente e falha do banco. Regressões F0/T0-R2 verificam tentativas/fases, orçamento, migração, reserva anterior ao domínio e recuperação; protocolo dos adaptadores cobre consumidores comuns.

Comando dirigido: `uv run --locked python -m pytest tests/backend/test_f2.py tests/backend/test_t2.py tests/backend/test_f0.py tests/backend/test_t0_r2.py tests/integration/test_adapter_protocol.py`. **44 aprovados em SQLite**, 252,01 s, incluindo os nove cenários F2 e 35 regressões pertinentes. Um aviso de depreciação Starlette/HTTPX permanece.

## Portabilidade e limites

PostgreSQL não executado: docker ps não alcança dockerDesktopLinuxEngine, com pipe ausente. A rejeição no contrato ocorre antes do banco e é verificada em SQLite, mas não constitui homologação PostgreSQL de busca, locale ou driver. A comparação entre bancos continua obrigatória no bloco H. A regra de case/acentos do SQL não foi normalizada: os testes T2 medem expectativas distintas por banco.

A verificação desta rodada é dirigida ao contrato alterado, busca, rastreamento e consumidores envolvidos. A última suíte completa histórica é F0, com 231 aprovados; não é resultado antecipado do F2. A nova suíte completa permanece prevista no fechamento do bloco principal F. Nenhuma verificação existente foi removida.

Sem aplicação em base operacional ou atualização de corpus real. Os testes usam fixtures e bancos sintéticos temporários. Revisão manual do responsável/CTO e homologação de agentes continuam separadas. F3, APIs e dependências não foram iniciados nesta entrega.

Estado: F2 implementado e verificado localmente em SQLite; 44 testes dirigidos aprovados. PostgreSQL e aceite manual pendentes; F3 aguarda solicitação específica.


## Fechamento das verificações

- `uv run --locked python -m pytest tests/backend/test_f2.py tests/backend/test_t2.py tests/backend/test_f0.py tests/backend/test_t0_r2.py tests/integration/test_adapter_protocol.py`: **44 aprovados**, 252,01 s; nove casos novos e 35 regressões pertinentes.
- `uv run --locked python -m ruff check .` e `uv run --locked python -m ruff format --check .`: aprovados.
- `uv run --locked python -m scripts.export_openapi`: cópia regenerada; `uv run --locked python -m scripts.export_openapi --check`: aprovado.
- `uv run --locked python -m scripts.validate_repository` e `git diff --check`: aprovados após documentação. Alteração funcional limitada ao contrato query; SQL e demais regras da busca preservados.
- Suíte completa não repetida nesta rodada dirigida; nova execução permanece prevista no fechamento principal F. O resultado histórico F0 de 231 não é evidência nova de F2. PostgreSQL não executado por indisponibilidade do Docker Linux. Um aviso Starlette/HTTPX permanece.

F2 encerrado como implementação/verificação local, com compatibilidade e portabilidade explicitadas. Sem aplicação operacional, publicação ou revisão automática. F3 não iniciado.

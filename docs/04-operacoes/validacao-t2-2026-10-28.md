# T2 — buscar_documentos

Data: 28/10/2026. Worktree oficial team/backend. Estado: implementado e verificado localmente em SQLite. Revisão manual do responsável pendente.

## Escopo e fluxo

Somente T2 do [plano](../02-arquitetura/backend-plano-lacunas.md). Não acrescenta filtros, ranking, embeddings, normalização Unicode, rotas ou migração. Alterações anteriores preservadas.

Cliente injeta contexto → backend valida reserva/concessões e identidade lógica T0 → consulta processo/versões → busca substring no índice com processo/corpus antes de LIMIT → valida os chunks selecionados contra chaves e texto da linha → confere envelope, unicidade e quantidade → registra sucesso → cliente valida modelo, contexto da requisição e limite pedido → entrega JSON ao adaptador.

SearchResult recusa chunks fora do processo/corpus, IDs de chunk repetidos e mais de 20 resultados. Servidor e clientes também conferem o limit específico da chamada (padrão 5, faixa 1–20). Um envelope internamente consistente de outra execução é recusado. Query e contexto não são escolhidos pelo backend em nome do modelo; permanecem os contratos existentes.

IDs do índice, documento, processo/corpus e texto do payload devem coincidir com as colunas efetivamente consultadas. Campos de página/offset continuam sob validação de Chunk. Isso não substitui conferência semântica do documento original nem recalcula sua extração/hash.

## Transferência de dados

- items[].document_id e page alimentam ler_documento.
- document_id, chunk_id e page compõem Evidence para uma escrita ou fonte declarada.
- source/text/offsets permitem rastrear o trecho no corpus preparado por Documentos.
- Não é imposto roteiro fixo de ferramentas ao agente.
- export_completeness e warning permanecem na resposta; lista vazia não comprova ausência no processo original.

## Contratos e respostas

| HTTP | Significado |
| --- | --- |
| 200 SearchResult | Busca concluída, inclusive items=[] |
| 401/403 | Credencial ou contexto/concessão/reserva não autoriza chamada |
| 404 | Processo/corpus autorizado não localizado; não é a resposta para busca sem correspondência |
| 409 | Versão, estado, orçamento ou identidade da chamada incompatível |
| 422 | Entrada inválida; inclui tipos e limites já definidos |
| 500 invalid_response | Índice/payload/resposta inconsistente; retryable=false, sem dados rejeitados |
| 503 storage_unavailable | Banco indisponível; retryable=true, preservar corpo/IDs no retry |

O código invalid_response já foi introduzido em T1; T2 declara-o também no OpenAPI de busca. Sucesso válido mantém o JSON anterior. Clientes comuns recusam respostas inválidas como ToolCallError definitivo, sem eco de conteúdo. Seus chamadores recebem os mesmos dicionários válidos.

Mudanças de recuperação e contratos precisam de revisão de Backend, Documentos, Hermes e LangGraph antes de integração compartilhada. Não houve acionamento do Astra.

## Busca literal e portabilidade

Preservados SQLAlchemy icontains(autoescape=True), filtro de processo/corpus antes do limite e ordenação por document_id/chunk_id. Os caracteres %, _ e / são pesquisados literalmente, inclusive combinados. Busca não remove acentos, não aplica casefold Python e não converte o corpus nesta entrega.

O teste sintético AÇÃO Café mede correspondência exata e diferenças de caixa Unicode. SQLite padrão costuma converter caixa apenas em ASCII: AÇÃO e Café correspondem; ação e CAFÉ não; cafe não equivale a Café. PostgreSQL com locale UTF-8 apropriado pode converter caixa Unicode, mas isso depende da configuração/locale e não elimina acentos. A homologação PostgreSQL deve registrar versão, LC_CTYPE/collation e resultados destas consultas antes de comparar agentes; não assumir equivalência entre bancos.

PostgreSQL não executado nesta rodada: Docker Linux parado. O teste inclui as expectativas do ambiente PostgreSQL UTF-8 previsto, ainda pendentes de confirmação nessa configuração. SQLite não serve como comprovação do comportamento PostgreSQL.

## Verificações e limitações

Cenários integrados previstos: outro processo e outra versão com termos iguais antes do limite, repetição determinística, curingas literais, busca vazia com cobertura parcial, índice corrompido, duplicatas, limite específico, contexto estrangeiro, erro de banco seguro, Unicode e consumidores HTTP existentes.

As variações de índice dos testes são exclusivamente sintéticas e temporárias; não alteram fixtures de corpus ou dados reais. Registro final dos comandos e resultados abaixo ao concluir. T3 não iniciado. Sem commit, push, PR ou deploy.


## Resultados finais

- `uv run --locked python -m pytest tests/backend/test_t2.py tests/backend/test_tools.py tests/integration/test_adapter_protocol.py`: 23 aprovados em SQLite (93,48 s).
- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **123 testes aprovados** (327,25 s); um aviso de depreciação Starlette/HTTPX.
- Depois da suíte completa, somente a fixture do teste de isolamento foi reforçada com document_id externo AAA-FOREIGN/AAA-CORPUS, garantindo ordenação anterior aos documentos autorizados. `pytest tests/backend/test_t2.py -k scope_precedes_limit`: 1 aprovado (6,46 s). Nenhuma lógica de produção mudou após aquela suíte.
- Ambiente local confirmado: Python 3.12.10, SQLite 3.49.1. Variações de caixa Unicode verificadas pelo cenário integrado; não houve teste PostgreSQL.
- OpenAPI versionado conferido; links, formato e diff revistos depois da documentação.
- Docker Linux continua indisponível: PostgreSQL, sua locale/collation e concorrência nesse banco permanecem pendentes.
- Os resultados não equivalem a revisão CTO nem homologação Hermes/LangGraph. T3 aguarda liberação do responsável.

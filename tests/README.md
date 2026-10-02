# Verificações

Execute `uv run --locked python -m scripts.dev check` na raiz.

- backend: contratos, erros, filtros de processo/corpus e comportamento das ferramentas.
- documents: rastreabilidade dos chunks, parâmetros, ingestão idempotente e imutabilidade.
- integration: ingestão → commit → outra engine → consulta/leitura pela API.

Por padrão os testes usam SQLite em diretórios temporários. TEST_DATABASE_URL permite banco PostgreSQL dedicado a testes; os IDs são exclusivos, e os testes não apagam tabelas/dados existentes. Não aponte para banco de pesquisa. A CI tem job PostgreSQL separado.

[Teste de integração](integration/README.md). Testes devem cobrir riscos reais, sem métricas artificiais de cobertura.

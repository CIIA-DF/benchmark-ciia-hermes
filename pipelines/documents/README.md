# Pipeline de documentos

Implementado: carregar JSON sintético paginado, calcular hash do arquivo e gerar chunks com IDs/offsets determinísticos. [Código](ingest.py). Extração PDF, OCR e embeddings estão planejados.

`uv run --locked python -m scripts.dev demo` ingere a fixture no banco local. `uv run --locked python -m scripts.dev test-documents` verifica rastreabilidade e repetição. Texto não pode atravessar páginas. Alterar conteúdo/parâmetros requer nova corpus_version.

[Guia da equipe](../../docs/03-equipes/documentos.md) · [Contratos](../../contracts/README.md). Corpus real deve ficar fora do Git e passar por autorização e preparação acordadas.

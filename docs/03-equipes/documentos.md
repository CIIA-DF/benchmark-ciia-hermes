# Documentos (RAG)

Integrantes: 3 | Monitor: André Vital. Branch: `team/documentos`.

- **Monitor:** André Vital
- **Integrantes:**
  - Victor Hugo Silva Moraes (5° semestre S.I.)
  - Vinícius Melo Maciel (5° semestre de sistemas de informação)
  - Lucas Farias de Sousa (5° semestre de sistemas de informação)

## Objetivo e responsabilidades

Transformar exportações autorizadas em corpus rastreável e com qualidade de recuperação conhecida.

Inventário, extração, qualidade, chunking, metadados, completude e preparação da recuperação. Conferir manualmente evidências e falhas de OCR.

Limites: Não implementar regras de negócio/escritas do backend nem escolher ferramentas pelo agente. Recuperação é interface compartilhada com Backend; mudanças exigem revisão conjunta.

## Entradas, saídas e dependências

Recebe exportações aprovadas e tarefas de Metodologia; entrega textos paginados, manifestos, hashes, chunks e relatório de cobertura/qualidade.

Backend define contrato de ingestão e filtros; Metodologia fornece consultas/evidências esperadas; Infra fornece armazenamento privado.

Pastas: pipelines/documents/, examples/ (somente sintéticos), tests/documents/; contracts/ em revisão conjunta.

## Estudar e executar

Python, JSON, PDF/OCR, hashes, offsets, chunking, busca textual; depois embeddings e pgvector.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev test-documents
```

Use `uv run --locked python -m scripts.dev check` antes do PR.

## Primeiras tarefas

1. Conferir a página e offsets de todos os chunks da demo; anexar evidência à tarefa.
2. Adicionar um documento sintético com tabela e uma consulta com origem esperada; teste deve detectar perda de conteúdo.
3. Propor manifesto de exportação com completude e revisar o contrato com Backend antes de extrair PDFs.

## Critério de conclusão

Documento rastreável, repetição sem duplicação, erro detectável e pelo menos uma consulta com referência conferida. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

# Documentos

Pessoas propostas: 3. Branch: `team/documentos`.
Responsável nominal: **a preencher**. Integrantes: **a preencher**. Revisor: **a preencher**.

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

Primeiro siga [instalação](../getting-started.md) e execute a demo. Comando da frente:

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

[Backlog conjunto](../backlog.md) · [Git](../git-workflow.md) · [Contratos](../../contracts/README.md)

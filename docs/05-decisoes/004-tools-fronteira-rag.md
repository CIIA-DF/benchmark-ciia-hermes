# ADR 004 — tools como operações de negócio e fronteira RAG

Data: 24/10/2026. Estado: implementado localmente, revisão conjunta pendente.
Responsáveis: Backend e Documentos/RAG.

## Contexto e decisão

O guia pp. 4/8–11 separa decisão do agente, execução de ferramenta e preparação
documental. Entregar primeiro cada tool junto de endpoint e teste permite integração
sem depender do chat. A base local tinha consultas acopladas aos handlers HTTP.

ToolService concentra operações e CorpusRepository concentra o acesso ao corpus.
Autorização e transação precedem a consulta. Escritas usam o serviço transacional
de execução existente. Catálogo exporta argumentos públicos sem contexto privilegiado.

## Alternativas e consequências

Não criar uma segunda API CRUD genérica nem um serviço RAG remoto sem contrato
da equipe. Reaproveitar o banco e a busca literal existentes reduz duplicação.
A substituição da recuperação exige testes de fontes/filtros e revisão de RAG.
Não implica implementar OCR, embeddings ou mudar os schemas documentais.

Ver [TDD](../02-arquitetura/backend-tdd.md). Complementa o ADR 003; não o substitui.

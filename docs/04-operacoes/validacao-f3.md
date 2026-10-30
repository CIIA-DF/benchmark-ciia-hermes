# F3 — ler_documento

F3 do [plano vigente](../02-arquitetura/backend-plano-blocos.md). Worktree oficial team/backend. Relatório conciso conforme preferência do responsável.

## Entrega

Integração existente de T3 com F0 preservada. Não foi reproduzida nova falha funcional. Alterações: nove testes integrados e documentação. Código de produção, modelos, OpenAPI e migrações permanecem iguais.

Fontes: [T3](validacao-t3.md), [F0](validacao-f0.md) e [ADR 008](../05-decisoes/008-tentativas-fisicas-tools.md).

## Workflow e contratos

1. Inventário fornece document_id. Busca fornece document_id/chunk_id/page.
2. Cliente injeta contexto e credenciais técnicas. ReadInput recebe document_id e pages opcional.
3. F0 registra UUID físico. Autorização confirma reserva lógica antes da consulta ao domínio.
4. Servidor valida documento armazenado, identidade e páginas. Seleção retorna ordem numérica documental.
5. Cliente valida DocumentResult, contexto, documento pedido e conjunto exato de páginas.
6. Texto/origem/página fundamentam análise. Referências de chunks continuam vindo da busca; leitura não fabrica chunk_id.

Sem filtro, retorna todas as páginas armazenadas. Com filtro, retorna exatamente as páginas pedidas, em ordem documental.

Páginas podem ter lacunas: pedido [7,1] retorna [1,7]. Página 2 ausente não pode ser inferida pela quantidade.

sha256 permanece o hash registrado do documento completo. Não representa hash do subconjunto nem recalcula o arquivo original.

Leitura parcial não comprova completude do arquivo original, leitura humana, compreensão do modelo ou sustentação semântica.

ReadInput mantém contexto, document_id e páginas inteiras estritas, positivas e únicas. Lista explícita vazia é inválida.

DocumentResult mantém contexto e Document. Identidade, ordem, unicidade e correspondência com o pedido continuam protegidas por T3.

## Respostas e rastreamento

- 200: documento integral ou subconjunto válido.
- 404 not_found: documento ou página ausente no escopo autorizado.
- 422 validation_error: entrada inválida, incluindo pages=[].
- 500 invalid_response: documento, identidade ou resposta inconsistentes; erro seguro e definitivo.
- 503 storage_unavailable: banco indisponível; erro transitório.
- 401/403 e conflitos 409: regras comuns de credencial, reserva, contexto, versão, identidade e orçamento.

Cada requisição observada recebe UUID físico próprio. Reserva lógica e tentativa física compartilham ferramenta, ID lógico e hash dos argumentos.

Entrada válida usa hash do DTO canônico. Entrada recusada usa hash dos bytes recebidos, conforme T0/F0.

Consulta registra started e completed/failed. Não cria artefato nem fase effect_confirmed. client_received permanece null.

Repetição com mesmo ID/corpo mantém uma reserva e abre outra tentativa física. Não representa replay de escrita.

Ledger tool_calls permanece compatibilidade de estágios. Contagens físicas usam ToolTracking.history.

## Evidências

Novo [test_f3.py](../../tests/backend/test_f3.py): nove casos HTTP/banco.

Oito casos verificam leitura integral, parcial, páginas não contíguas, documento ausente, página ausente, corrupção, entrada inválida e falha SQL.

Conferências: conteúdo/páginas exatas, hash integral preservado, resposta aceita pelo cliente e erros sem conteúdo rejeitado.

Banco: uma reserva e tentativa coerentes por caso; HTTP/código preparados corretos; fases esperadas; nenhum artefato; recebimento desconhecido.

Nono caso: orçamento 1, duas leituras parciais iguais. Resultado idêntico, uma reserva lógica e dois UUIDs físicos.

Regressões T3 cobrem documento/contexto/páginas adulterados, ordem, duplicatas, isolamento e clientes. F0 cobre rastreamento, migração, rollback e transporte.

Comando dirigido:

```sh
uv run --locked python -m pytest tests/backend/test_f3.py tests/backend/test_t3.py tests/backend/test_f0.py tests/integration/test_adapter_protocol.py
```

**40 aprovados em SQLite**, 206,68 s. Inclui nove cenários F3 e 31 regressões pertinentes.

## Limitações e aceite

PostgreSQL não executado: Docker Linux indisponível; pipe dockerDesktopLinuxEngine ausente. SQLite não homologa PostgreSQL, concorrência ou recuperação.

Runtimes reais e revisão CTO/Astra permanecem pendentes. Backend, Documentos e agentes devem revisar o aceite antes da integração compartilhada.

Suíte completa não repetida: esta entrega altera somente testes/documentação. Fechamento principal F prevê nova suíte completa.

Última suíte completa histórica: F0, 231 aprovados. Não constitui resultado novo do F3.

Fixtures e bancos sintéticos temporários. Nenhum corpus real ou banco operacional foi alterado. Nenhuma verificação existente foi removida.

Histórico e alterações anteriores preservados. Sem commit, merge, push, PR, publicação ou revisão automática.

Estado: F3 preservado e verificado localmente. PostgreSQL e aceite manual pendentes. F4 aguarda liberação.


## Verificações finais

- Testes dirigidos: 40 aprovados, 206,68 s.
- `uv run --locked python -m ruff check .`: aprovado.
- `uv run --locked python -m ruff format --check .`: aprovado.
- `uv run --locked python -m scripts.validate_repository`: aprovado.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado.
- `git diff --check`: aprovado.

Um aviso de depreciação Starlette/HTTPX permanece. Suíte completa não repetida; 231 aprovados pertencem ao histórico F0.

Código funcional e contratos preservados. F3 encerrado como integração verificada localmente. F4 não iniciado.

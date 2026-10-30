# F4 — consultar_requisitos

F4 do [plano vigente](../02-arquitetura/backend-plano-blocos.md). Worktree oficial team/backend. Relatório conciso conforme preferência do responsável.

## Entrega

Integração T4/F0 preservada. Nenhuma falha funcional nova foi reproduzida. Entrega: sete testes HTTP/banco e documentação.

Código de produção, contratos, OpenAPI e migrações permanecem iguais. Fontes: [T4](validacao-t4.md), [F0](validacao-f0.md) e [ADR 008](../05-decisoes/008-tentativas-fisicas-tools.md).

## Workflow e contratos

1. Importação administrativa mantém checklist imutável por processo, corpus e requirements_version.
2. Cliente injeta contexto do run e credenciais técnicas na consulta.
3. F0 registra UUID físico. Servidor autoriza e confirma reserva lógica antes do domínio.
4. Consulta filtra pelas três chaves. Cada payload Requirement precisa coincidir com a chave persistida.
5. RequirementsResult exige itens não vazios e IDs únicos. Cliente confere contrato e contexto da execução.
6. items[].requirement_id pode alimentar registrar_pendencia.requirement_id no mesmo escopo.
7. Operador consulta o artefato autorizado e confere requisito, conteúdo e recibo.

Requirement mantém requirement_id, description e source obrigatórios. Importação e modelos de entrada/saída não mudaram.

O agente escolhe o requisito aplicável. Existência do item não comprova qualidade metodológica, leitura do modelo ou sustentação das evidências.

## Respostas

- 200: checklist presente, não vazio, único e versionado.
- 404 not_found: checklist ausente no escopo autorizado.
- 500 invalid_response: payload ou identidade persistida inconsistente; erro seguro, retryable=false.
- 503 storage_unavailable: falha do banco; retryable=true.
- 401/403: credencial, lease, concessão ou contexto recusados.
- 409: estado, versão do processo, identidade ou orçamento incompatíveis.
- 422: entrada inválida. Na pendência, requisito estrangeiro também é validation_error.

Consulta não cria artefato. Sua tentativa registra started e completed/failed, sem effect_confirmed. client_received permanece null.

Reserva e tentativa física compartilham ferramenta, ID lógico e hash dos argumentos. Ledger tool_calls continua representando estágios de compatibilidade.

## Evidências

Novo [test_f4.py](../../tests/backend/test_f4.py): sete casos.

Seis casos cobrem sucesso, ausência, JSON null, identidade divergente, payload duplicado sob outra chave e falha SQL.

Conferências: HTTP/código, retorno seguro, itens válidos e únicos, reserva durável, hash e fases físicas coerentes, nenhum artefato.

Sétimo caso insere requisitos sintéticos estrangeiros por processo, corpus e versão. A consulta retorna somente o item autorizado.

Pendência estrangeira recebe 422 e não persiste. Requisito consultado gera um artefato, conferido por GET independente.

Três requisições de tools têm UUIDs distintos. Consulta termina completed; escrita estrangeira termina failed; escrita válida registra effect_confirmed e completed.

Regressões T4 verificam importação imutável, campos inválidos, unicidade e respostas estrangeiras recusadas pelo cliente. F0 verifica fases, orçamento, migração e recuperação.

Comando dirigido:

```sh
uv run --locked python -m pytest tests/backend/test_f4.py tests/backend/test_t4.py tests/backend/test_f0.py tests/integration/test_adapter_protocol.py
```

**36 aprovados em SQLite**, 154,75 s. Inclui sete cenários F4 e 29 regressões pertinentes.

## Limitações e aceite

PostgreSQL não executado: Docker Linux indisponível, pipe dockerDesktopLinuxEngine ausente. SQLite não homologa concorrência, migração ou recuperação PostgreSQL.

Runtimes reais e revisão CTO/Astra permanecem pendentes. Backend, Documentos, agentes e Metodologia devem revisar o aceite antes da integração compartilhada.

Suíte completa não repetida: entrega altera somente testes/documentação. Nova suíte completa permanece prevista no fechamento principal F.

Última execução completa histórica: F0, 231 aprovados. Esse número não é evidência nova de F4.

Fixtures e bancos sintéticos temporários. Nenhum corpus real ou banco operacional alterado. Alterações anteriores e verificações existentes preservadas.

Sem commit, merge, push, PR, publicação ou revisão automática. O teste de pendência verifica consumo do checklist; não antecipa o aceite F5.

Estado: F4 preservado e verificado localmente. PostgreSQL e aceite manual pendentes. F5 aguarda liberação.


## Verificações finais

- Testes dirigidos: 36 aprovados, 154,75 s.
- `uv run --locked python -m ruff check .`: aprovado.
- `uv run --locked python -m ruff format --check .`: aprovado.
- `uv run --locked python -m scripts.validate_repository`: aprovado.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado.
- `git diff --check`: aprovado.

Um aviso de depreciação Starlette/HTTPX permanece. Suíte completa não repetida; 231 aprovados pertencem ao histórico F0.

F4 encerrado como integração verificada localmente. Código funcional e contratos preservados. F5 não iniciado.

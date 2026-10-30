# F1 — consultar_processo e rastreamento F0

Escopo: F1 do [plano vigente](../02-arquitetura/backend-plano-blocos.md), na worktree oficial team/backend. A solicitação repetida após interrupção foi tratada como a mesma tarefa; a inspeção inicial não encontrou alterações F1 parciais. Trabalho anterior preservado.

## Situação e entrega

A inspeção confirmou que consultar_processo já propaga o UUID físico da fronteira HTTP ao ToolService pelo F0. Reserva lógica ocorre antes do domínio; leitura/validação continua protegida por T1/T1-R. Não foi reproduzida nova falha de negócio que justifique alterar leitura, contrato ou cliente. Conforme o plano, esta entrega acrescenta aceite integrado específico e documentação, preservando a implementação funcional.

Arquivo de código novo: [test_f1.py](../../tests/backend/test_f1.py), com oito cenários HTTP/banco. Nenhum arquivo de produção, schema, dependência, rota, cabeçalho ou migração foi alterado no F1. O rastreamento vem de [F0](validacao-f0.md)/[ADR 008](../05-decisoes/008-tentativas-fisicas-tools.md); comportamento de domínio vem de [T1](validacao-t1-2026-10-28.md) e [T1-R](validacao-t1-r.md).

## Workflow, contratos e consumidores

Run reservado → contexto injetado pelo cliente e credenciais técnicas → requisição POST /tools/consultar_processo → UUID físico/started duráveis → autorização → vínculo lógico (run_id, tool_call_id, ferramenta e hash) confirmado antes do domínio → validação do processo/versionamento → inventário do mesmo processo/corpus → ProcessResult validado → resposta preparada completed/failed → cliente confere contrato e contexto.

Entrada permanece ToolContext com run_id UUID, process_id, corpus_version e requirements_version. Saída permanece ProcessResult com contexto, Process, cobertura/nota e inventory de InventoryItem. Processo deve corresponder ao envelope; inventário não admite IDs repetidos e suas fontes pertencem ao processo/corpus autorizado.

| Dado retornado | Consumidor e limite |
| --- | --- |
| Processo/corpus/versão | Contexto das demais ferramentas, conferido contra o run |
| inventory[].document_id | ler_documento; inventário não fornece todos os números de página |
| Inventário e cobertura/nota | Evidência de limitação documental; vazio não prova ausência no SEI original |
| Tentativa física e fases internas | ToolTracking.history, revisão e futura exportação; não são novos campos de ProcessResult |

Consulta não grava artefato. Por isso sua tentativa tem started e completed/failed, sem effect_confirmed de artefato. http_status/código representam a resposta preparada, e client_received permanece null. Ledger tool_calls continua como compatibilidade de estágios, sem substituir a fonte física do F0.

Modelos, OpenAPI e clientes síncrono/assíncrono permanecem compatíveis. As regressões existentes conferem resposta estrangeira/internamente inconsistente, inventário duplicado e cobertura. Revisão manual de Backend/Documentos/agentes continua separada; não houve acionamento automático do Astra/CTO.

## Catálogo e matriz de aceite

| Situação | HTTP/código | Reserva e tentativa |
| --- | --- | --- |
| Processo e inventário válidos | 200 ProcessResult | Reserva durável; uma tentativa física concluída |
| Inventário vazio | 200, inventory=[] | Cobertura/nota preservadas; não inventa artefato |
| Processo/corpus autorizado ausente | 404 not_found | Reserva antes da consulta; tentativa failed atribuída ao run |
| Processo válido com requirements_version divergente do run | 409 version_mismatch | Preserva vínculo lógico e tentativa failed |
| Processo incompleto, inclusive requirements_version ausente | 500 invalid_response | JSON seguro, retryable=false, tentativa failed e reserva mantidas |
| Documento do inventário com identidade estrangeira | 500 invalid_response | Sem retorno de inventário inconsistente, artefato ou conteúdo rejeitado |
| Banco falha na consulta do processo | 503 storage_unavailable | retryable=true; resposta/falha ligadas à mesma tentativa física |

401/403 de autenticação/contexto/reserva e 422 de entrada seguem regras comuns; contexto de requisição diferente do run não equivale ao 409 de versão armazenada divergente. 409 de orçamento/identidade lógica também permanece distinto. Esta entrega não amplia os envelopes gerais do framework/proxy, tema do A0.

## Evidências integradas

Sete casos parametrizados em test_f1.py verificam a matriz acima: normal, inventário vazio, ausência, versão, metadados inválidos, inventário inválido e banco indisponível. Além do status/código, cada caso compara diretamente no banco:

- exatamente uma tentativa física, ferramenta/ID lógico/hash coerentes com a reserva durável e com digest(context);
- HTTP e código preparados iguais ao retorno observado no teste;
- fases started/completed ou started/failed; nenhum artifact_id ou effect_confirmed;
- client_received=null e finished_at conhecido;
- nenhum artefato criado, erros sem marcador de conteúdo privado e resposta válida aceita pelo consumidor compartilhado.

O oitavo caso usa orçamento lógico 1: consulta de processo sintético com JSON null falha com 500; após restauração administrativa somente do banco temporário de teste, a mesma entrada/ID recupera a consulta com 200. Há duas identidades físicas e uma reserva lógica, sem novo consumo de orçamento. Não se implementa reparo automático nem se modifica corpus real.

Regressões dirigidas: test_t1.py (processo/inventário/cliente), test_t1_r.py (payloads inválidos e auditoria), test_f0.py (tentativas/fases/migração/recuperação), e test_adapter_protocol.py (consumo compartilhado). Comando: `uv run --locked python -m pytest tests/backend/test_f1.py tests/backend/test_t1.py tests/backend/test_t1_r.py tests/backend/test_f0.py tests/integration/test_adapter_protocol.py`. **50 aprovados em SQLite**, 217,78 s, incluindo os oito casos novos de F1. Um aviso de depreciação Starlette/HTTPX permanece.

## Limitações e verificações

PostgreSQL não executado: docker ps não alcança dockerDesktopLinuxEngine (pipe ausente). SQLite não homologa travas, concorrência ou migrações em PostgreSQL. Conexão real Hermes/LangGraph e interpretação metodológica continuam pendentes.

A verificação funcional desta rodada é dirigida aos contratos e componentes envolvidos. A última suíte completa histórica é F0, com 231 aprovados; esse número não é apresentado como execução F1. Como não houve mudança de produção, a suíte completa não será repetida nesta entrega de aceite/documentação. O fechamento do bloco principal F prevê nova suíte completa e revisão manual, conforme o plano.

Sem nova migração ou aplicação em base operacional. Sem commit, merge, push, PR, publicação ou revisão automática por agentes. A sincronização de branches antes de PR permanece coordenada e manual. A0/APIs e F2 não foram iniciados; o NUL da busca pertence ao próximo sub-bloco.

Estado: integração F1 preservada e verificada localmente em SQLite, com 50 testes dirigidos aprovados. Aceite manual e PostgreSQL separados; F2 aguarda solicitação específica.


## Fechamento das verificações

- `uv run --locked python -m pytest tests/backend/test_f1.py tests/backend/test_t1.py tests/backend/test_t1_r.py tests/backend/test_f0.py tests/integration/test_adapter_protocol.py`: **50 aprovados**, 217,78 s; oito novos cenários e 42 regressões pertinentes.
- `uv run --locked python -m ruff check .` e `uv run --locked python -m ruff format --check .`: aprovados.
- `uv run --locked python -m scripts.validate_repository` e `uv run --locked python -m scripts.export_openapi --check`: aprovados após a documentação; nenhum schema público mudou.
- `git diff --check`: aprovado. Diff desta entrega restrito a teste F1 e documentação; código funcional de produção preservado.
- Suíte completa não repetida nesta rodada de aceite/documentação; a última execução completa F0 teve 231 aprovados e é referência histórica. PostgreSQL não executado por indisponibilidade do Docker Linux. Um aviso Starlette/HTTPX permanece.

F1 encerrado como integração e verificação local. Sem publicação, alteração de banco operacional ou revisão automática. F2 e APIs não iniciados; liberação do responsável continua manual.

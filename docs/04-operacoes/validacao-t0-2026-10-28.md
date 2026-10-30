# T0 — Base compartilhada das ferramentas

Data: 28/10/2026. Implementação local na worktree oficial team/backend.
Estado: implementado e verificado localmente em SQLite. PostgreSQL e revisão do responsável pendentes.

## Escopo e fluxo

Bloco autorizado: T0 do [plano](../02-arquitetura/backend-plano-lacunas.md). Sem implementação dos blocos T1–T6 ou A0–A9. Preservadas as alterações locais anteriores e a auditoria histórica.

Fluxo: cliente gera ID lógico → servidor autentica/confere contexto e concessões → reserva durável de (run_id, tool_call_id, ferramenta, hash) → commit da reserva → nova transação revalida reserva/concessões → executa leitura/escrita → confirma efeito e tentativa → cliente valida o modelo de saída antes de devolver JSON ao adaptador.

A reserva durável impede que rollback, falha antes do efeito ou reinício libere um ID para outra operação. Mesmo ID/ferramenta/entrada permite retry; entrada ou ferramenta diferente gera 409 idempotency_conflict. ID novo além do orçamento gera 409 budget_exceeded sem efeito. Tentativas seguem registradas separadamente. Chamada recusada pelo orçamento não cria reserva; pode ser tentada se o orçamento administrativo aumentar. Entradas inválidas atribuíveis à reserva vinculam ID ao hash dos bytes rejeitados; para corrigir, o cliente precisa de ID novo. Entradas válidas usam hash do modelo normalizado, como antes.

## Contratos e compatibilidade

- Catálogo único contém ToolSpec(input_model, description, output_model). Nomes, descrições e schemas enviados ao modelo permanecem iguais. Consumidores internos que desempacotavam tuplas devem usar os campos nomeados.
- Servidor valida saídas de leitura e recibos antes de confirmar o sucesso; clientes síncrono/assíncrono validam todo sucesso pelo modelo da ferramenta.
- JSON válido continua sendo devolvido como dicionário; resposta 200 malformada gera ToolCallError definitivo, sem eco do conteúdo e sem retry automático. Um efeito pode já existir: recuperar pelo recibo/artefato, sem inventar nova chave de escrita.
- Mantidos perfis, concessões, formato de erros, evidências e identidade idempotente de escrita. A0 (uniformização HTTP) e A7 (validar declaração experimental) continuam pendentes.
- Atualização de catálogo e clientes exige revisão de Backend, Hermes e LangGraph antes de integração compartilhada. Não houve publicação nem acionamento do Astra.

## Migração 0005

Nova tabela logical_tool_calls; revisões anteriores preservadas. Backfill usa a primeira tentativa registrada de cada ID; tentativas posteriores inconsistentes permanecem na auditoria, mas não redefinem a identidade. Sem apagar corpus, artefatos ou histórico. IDs antigos já consumidos continuam contabilizados, inclusive registros de recusas existentes.

Reserva de ID e execução são duas transações deliberadas. Se o processo cair entre elas, o orçamento permanece consumido e o retry da mesma entrada pode prosseguir enquanto a reserva do run estiver válida. Depois do término, novas tools continuam recusadas.

Downgrade para 0004 remove as reservas duráveis, inclusive as que não chegaram a gerar tentativa; não executar sobre banco em uso. Backup e atualização de banco existente são administrativos. Esta entrega aplicou migrações apenas nos bancos sintéticos de verificação/demonstração.

## Evidências previstas e observadas

- Regressões HTTP integradas: orçamento de uma chamada, troca de ferramenta/entrada, rollback de evidência, falha de armazenamento antes do efeito, recusa de corpo inválido e duas escritas concorrentes com mesmo ID.
- Migração: downgrade/upgrade preserva tentativas e reconstitui identidade; cenário de corpus legado permanece coberto pela suíte existente.
- Clientes síncrono e assíncrono: perda de resposta depois de commit, mesmo corpo/ID no retry, um único artefato, replay confirmado e duas tentativas no histórico.
- Seis modelos de saída: sucesso malformado recusado sem expor conteúdo. Doubles antigos de retry passaram a devolver um ProcessResult completo.
- PostgreSQL 17 não executado: Docker Linux parado. Não tratar concorrência SQLite como homologação PostgreSQL.
- Sem homologação de agentes/LLM reais, atualização de dependências ou revisão CTO.

Os resultados finais dos comandos constam ao fim deste registro. O achado 03 possui correção local; aceite conjunto e PostgreSQL permanecem pendentes. Os demais achados não foram encerrados.


## Resultados finais

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e 95 testes aprovados em SQLite (148,97 s).
- Dois cenários adicionais `pytest tests/backend/test_t0.py -k lost_response`: aprovados nos clientes síncrono/assíncrono (27,83 s). Entraram depois da coleta da suíte completa; não são apresentados como parte daqueles 95 testes.
- `uv run --locked python -m scripts.tools_demo`: seis tools verificadas; dois artefatos com hash e replay confirmados; sem agente real.
- Ruff final sobre todos os arquivos, formato, validador e OpenAPI conferidos depois da inclusão dos dois cenários.
- `git diff --check`: sem erros de whitespace; alterações anteriores preservadas.
- Aviso mantido: depreciação Starlette/HTTPX. Sem instalar dependências fora do lock para eliminá-lo.
- Docker indisponível; PostgreSQL, restauração operacional e revisão manual do responsável não concluídos. Não houve commit/push/PR/deploy.


## Correção posterior T0-R1

A revisão dirigida identificou que o can_write do worker era um snapshot. A releitura dos perfis na transação do efeito foi corrigida posteriormente; ver [evidências T0-R1](validacao-t0-r1.md). T0-R2 e T1-R continuam pendentes; este registro histórico não representa aceite dessas falhas.


## Correção posterior T0-R2

A consulta de domínio acontecia antes de confirmar a reserva lógica. A ordem foi corrigida posteriormente; ver [T0-R2](validacao-t0-r2.md). Erros de versão/ausência preservam identidade e orçamento. T1-R e aceite PostgreSQL/manual continuam pendentes.

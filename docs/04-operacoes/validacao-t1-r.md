# T1-R — Validação do processo antes do acesso aos campos

## Escopo e causa

Correção local na worktree oficial team/backend, fechando a falha relatada na revisão de D0/T0/T1. Antes, CorpusRepository.process acessava requirements_version diretamente no JSON armazenado; campo ausente gerava KeyError fora do fluxo de ToolFailure, resultando em 500 genérico e sem tentativa auditada.

Mudança de implementação concentrada na fronteira de leitura do processo. Mantidas as correções T0-R1 (perfis atuais na escrita) e T0-R2 (commit lógico anterior ao domínio). Sem nova migração, campos de sucesso ou códigos de erro. O OpenAPI foi atualizado para declarar o invalid_response existente nas rotas que consultam esse processo compartilhado. [Plano](../02-arquitetura/backend-plano-lacunas.md).

## Fluxo e semântica

1. Buscar a linha de processo/corpus pela chave autorizada. Linha ausente mantém 404 not_found.
2. Linha presente é validada integralmente com Process antes de acessar campos. JSON null não é confundido com linha ausente; é metadado inválido, assim como objeto incompleto, estrutura errada ou identidade divergente.
3. Conferir process_id/corpus_version do modelo contra o escopo selecionado. Inconsistência gera ToolFailure 500 invalid_response com mensagem estática e retryable=false, sem dados do payload.
4. Somente depois da validação, comparar requirements_version. Valor válido divergente mantém 409 version_mismatch.
5. Retornar dicionário serializado do modelo validado, preservando os contratos dos consumidores.
6. Nas tools, a consulta acontece depois do commit da reserva T0-R2 e dentro da transação do efeito. A falha segue para ToolService.failed, que registra a tentativa após rollback; a reserva lógica permanece confirmada.

SQLAlchemyError não é capturado como validação: preserva o tratamento 503 storage_unavailable. Não foi introduzido catch genérico de exceções. Recursos inválidos não produzem sucesso nem artefato. Reparar os dados é operação administrativa explícita; retry automático de invalid_response continua desabilitado.

A fronteira é compartilhada: as seis tools podem retornar invalid_response ao encontrar processo corrompido. O OpenAPI documenta o 500 seguro nas seis tools e nas criações de conversa/run/mensagem que também consultam processo. Isso não implementa A0 nem promete que todos os 500 inesperados/framework usam esse envelope.

## Evidências integradas

Novo arquivo tests/backend/test_t1_r.py, exclusivamente com corpus temporário sintético:

- Sete corrupções: requirements_version ausente ou inválido; process_id ou corpus_version divergentes; payload como lista, string ou JSON null. Exigem HTTP 500 application/json, invalid_response, retryable=false, sem campos/dados rejeitados, reserva lógica mantida e tentativa auditada com hash correspondente.
- Orçamento 1 nos cenários de corrupção. Após reparo do payload, mesma consulta/ID volta a 200, histórico 500/200 e uma única reserva lógica, sem nova cobrança.
- requirements_version ausente exercitado nas seis tools, com tentativa auditada por operação e nenhum artefato. Contrato 500 ToolError conferido no OpenAPI dessas tools.
- Versão válida divergente continua 409; inventário vazio continua 200; remoção da linha de processo continua 404. Essa ausência é distinta de payload JSON null.

Primeira execução dirigida: `uv run --locked python -m pytest tests/backend/test_t1_r.py tests/backend/test_t1.py tests/backend/test_t0_r2.py tests/backend/test_t2.py`: 41 aprovados em SQLite (101,38 s), um aviso de depreciação Starlette/HTTPX. Depois dessa rodada, os testes novos foram reforçados com orçamento explícito e conferência do OpenAPI; a suíte completa abaixo valida esse estado final.

## Limitações e liberação

Suíte completa concluída no estado final da implementação; resultados detalhados abaixo. PostgreSQL deve ser tratado separadamente: Docker Linux indisponível nas últimas verificações, sem equivalência presumida entre bancos.

Sem alteração do algoritmo de recuperação T2, sem implementação de T3, sem commit, push, PR ou deploy. Auditoria original e registros históricos preservados. Revisão CTO/Astra não acionada; aceite manual permanece com o responsável. Corrigir essas três falhas não encerra os demais achados da auditoria geral.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **145 testes aprovados** em SQLite (330,83 s), incluindo as regressões T0-R1/T0-R2/T1-R e consumidores existentes.
- A execução dirigida anterior teve 41 aprovados (101,38 s); não somar esses testes como casos distintos da suíte completa.
- OpenAPI versionado conferido após regeneração e documentação; diff dirigido sem erros de whitespace.
- PostgreSQL não executado: `docker ps` confirmou indisponibilidade do motor Docker Linux. Não declarar homologação PostgreSQL ou equivalência de concorrência a partir de SQLite.
- Mantido um aviso de depreciação Starlette/HTTPX; nenhuma dependência foi instalada fora do lock para removê-lo.
- Sem alteração de comportamento de T2 além da proteção da leitura compartilhada de processo inválido. T3 não iniciado.

Estado: T1-R implementado e verificado localmente, encerrando a repetição da suíte completa prevista para as três correções de implementação. O aceite manual do responsável e a homologação PostgreSQL continuam pendentes; os demais achados gerais de segurança permanecem conforme o plano.

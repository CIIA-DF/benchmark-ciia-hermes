# Fechamento local do bloco A — APIs

Data: 30/10/2026. Situação: fechamento local aprovado em SQLite, disponível para revisão manual.
Worktree: C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes. Branch: team/backend.
Escopo: A0–A13 do [plano vigente](../02-arquitetura/backend-plano-blocos.md). Revisão CTO/Astra permanece manual.

## Matriz de aceite por sub-bloco

As seleções abaixo são evidências individuais. Incluem regressões próximas e têm interseção; seus totais não devem ser somados.
A0 usou sua suíte completa histórica. Nesta sequência A6–A13, cada aceite e relatório foi fechado antes de iniciar o seguinte.

| Sub-bloco | Resultado implementado/verificado | Seleção dirigida | Evidências |
| --- | --- | --- | --- |
| A0 | Corpo de 1 MiB, erros seguros, Bearer/no-store e fronteira SSE | 26 | [A0](validacao-a0.md) |
| A1 | GET de artefatos valida integridade e propriedade | 14 | [A1](validacao-a1.md) |
| A2 | Resultado experimental reconciliado com histórico e efeitos | 19 casos distintos | [A2](validacao-a2.md) |
| A3 | Quota de 20 queued por operador, com replay anterior à quota | 12 | [A3](validacao-a3.md) |
| A4 | APIs de conversas e quota comum chat/benchmark | 17 | [A4](validacao-a4.md) |
| A5 | Expiração passiva queued em 300 s e preservação de histórico/parciais/artefatos | 18 | [A5](validacao-a5.md) |
| A6 | Claim exclusivo, prazo/grants e presença em polling vazio | 6 | [A6](validacao-a6.md) |
| A7 | Heartbeat renova presença e lease atomicamente com identidade atual | 10 | [A7](validacao-a7.md) |
| A8 | 20.000 eventos, vaga terminal, um desfecho e rollback de efeitos recusados | 11 | [A8](validacao-a8.md) |
| A9 | Cinco admissões SSE duráveis, TTL e limpeza ASGI | 14 | [A9](validacao-a9.md) |
| A10 | Configuração separada da presença de 60 s e modelo desconhecido explícito | 13 | [A10](validacao-a10.md) |
| A11 | Health executa SQL real com 200/503 e alcance limitado | 5 | [A11](validacao-a11.md) |
| A12 | Listagem confere estrutura/identidade concedida e vazio válido | 9 | [A12](validacao-a12.md) |
| A13 | Seis rotas HTTP, executor compatível e 1.000 admissões físicas por run | 32 | [A13](validacao-a13.md) |

## Workflow e dados compartilhados

1. Operador autenticado vê apenas processos/corpus concedidos e cria conversa ou run de benchmark.
2. POST de run/mensagem reserva uma vaga queued sob trava do operador; replay mantém a mesma execução.
3. Manutenção passiva encerra queued vencido como timed_out/queue_timeout, sem apagar histórico.
4. Claim autorizado registra presença e retorna contexto, histórico, run_id e run_token; 204 também registra polling válido.
5. Worker envia run_token nas tools, heartbeat, eventos e resultado. Heartbeat atualiza lease/presença sem renovar o prazo máximo do run.
6. Cada requisição física das seis tools recebe UUID próprio e, quando a lease identifica o titular, consome admissão do run antes do corpo.
7. ID lógico e hash vinculam a operação/reserva; retries mantêm essa identidade, mas criam nova tentativa física.
8. Leituras entregam processo, inventário, trechos, páginas e checklist tipados; evidências alimentam pendência/minuta sem impor cadeia fixa de tools.
9. Escrita confirma artefato/recibo/fase de efeito na mesma transação. GET do artefato valida sua integridade e autorização.
10. Eventos persistidos atualizam cursor e texto parcial; SSE autorizado usa lease próprio, preserva ordem e retoma pelo cursor.
11. Resultado experimental declara IDs, efeitos e artefatos que A2 confere contra o histórico observado; sucesso declarado não vira avaliação independente.
12. Finalização/timeout/limite terminal conserva um único done, parciais e efeitos anteriores. Recebimento pelo cliente continua desconhecido sem evidência.

## Mudanças públicas e catálogo de respostas

- StoredResult acrescenta queue_timeout e event_limit, reservados ao servidor; AgentResult do worker não os aceita.
- ExecutorCapability acrescenta enabled, worker_recent, last_seen_at, model e configuration_known.
  available continua configuração habilitada. Presença recente não comprova conexão atual ou inferência; model null e configuration_known false são desconhecimento explícito.
- ErrorCode resource_limit é comum às quotas. Clientes devem ler retryable e estado do run, sem repetir indiscriminadamente.
- Schemas, contratos compartilhados e OpenAPI executável foram atualizados. Consolidação editorial/versão ampla segue no bloco D; integrações amplas seguem em I.

| HTTP / evento | Significado no bloco A |
| --- | --- |
| 200 | Leitura/operação válida; GET de run failed/timed_out continua sendo leitura bem-sucedida |
| 201 / 202 | Conversa criada / run ou mensagem aceitos, sem prova de conclusão |
| 204 | Claim sem tarefa elegível, com presença registrada quando autorizado |
| 401 | unauthorized; challenge WWW-Authenticate: Bearer |
| 403 / 404 | Perfil, executor, grants, lease ou contexto recusados / recurso ausente ou fora do alcance |
| 405 | method_not_allowed com Allow, quando a admissão física não recusou antes |
| 409 | Estado/lease vencida, idempotência, versão ou orçamento lógico incompatível |
| 413 / 422 | Corpo acima de 1 MiB / entrada ou semântica inválida |
| 429 resource_limit, retryable true | Sem vaga de queued ou SSE; pode haver capacidade posterior |
| 429 resource_limit, retryable false | Teto físico do run ou excesso de evento; consultar snapshot |
| 500 | invalid_response para saída/persistência incoerente; internal_error para falha inesperada, ambos seguros |
| 503 | Banco indisponível ou executor desabilitado; observar código e retryable do envelope |
| stream_error após HTTP 200 | Falha após abrir SSE; mensagem/código seguros, encerramento e liberação da admissão |

Respostas privadas usam no-store. Last-Event-ID prevalece sobre after. X-Tool-Call-Id é identidade lógica, não autenticação.
X-Run-Token identifica a lease de execução; a lease SSE é interna e não exige novo cabeçalho público.

## Limites e migrações

| Controle | Valor / regra |
| --- | --- |
| Corpo HTTP | 1 MiB, incluindo recebimento em chunks |
| Fila por operador | 20 queued; RUN_MAX_QUEUED_PER_OPERATOR positivo |
| Prazo de fila | 300 s; RUN_QUEUE_TIMEOUT_SECONDS positivo, independente do prazo running |
| Eventos | 20.000 por run, incluindo servidor/tools/done; última vaga terminal |
| SSE | Cinco admissões válidas por operador entre processos; TTL 30 s, renovação quando restam até 15 s |
| Presença | Janela inclusiva de 60 s, com grants/perfil atuais em comum |
| Tentativas HTTP de tools | 1.000 admissões atribuíveis por run; erros/retries contam, recusas posteriores continuam auditadas |

0007 cria worker_presence sem inferir presença histórica. 0008 cria stream_leases sem inferir sessões existentes.
Migrações foram exercitadas em bancos sintéticos; não houve migração de banco operacional.
Histórico legado de eventos já acima do teto não é apagado/renumerado; seu encerramento conserva um único done além do histórico anterior.
Recusas físicas fazem a auditoria superar 1.000 linhas; esse total não é o número de admissões executáveis.
Ledger anterior ao F0 não é convertido em contagem física fictícia. A quota física não é rate limit global de tráfego anônimo.
Processo congelado pode manter socket aberto após perder lease SSE; ao retomar, não pode ressuscitar admissão expirada.
Falha SQL na limpeza SSE depende do TTL para recuperar capacidade. Queued expira na próxima manutenção, sem scheduler novo.

## Fechamento e validações finais

Comando de fechamento, executado somente após o aceite dirigido do A13:

```sh
uv run --locked python -m scripts.dev check
```

**390 testes aprovados em SQLite, sem falhas, em 1.328,12 segundos (22min08s).**
O comando completo levou 1.336,15 segundos (22min16s), incluindo lint, formato e validação documental.
Início: 30/10/2026 14:28:02 -03:00. Fim: 14:50:18 -03:00. Código final 0.
O pytest recebeu somente --durations=10 adicional pelo ambiente para registrar as fases mais lentas, sem reduzir a seleção.
Não houve repetição da suíte completa nesta sequência: uma execução aprovada no fechamento.

Evidências locais preservadas:

- tmp/a-final-check.log: resultado completo, aviso e dez maiores durações.
- tmp/a-final-check.exit: código 0.
- tmp/a-final-check-metadata.json: diretório, início/fim, duração total e código final.
- tmp/a12-directed.log e tmp/a13-directed.log: aceites dirigidos de 9 e 32 testes, respectivamente.

Lint global aprovado; 212 arquivos Python passaram na formatação. Links locais, YAML e invariantes aprovados.
OpenAPI foi conferido após as alterações executáveis e na conferência final. Whitespace Git e documentação final aprovados.
Portal: lint dirigido de app/chat/page.tsx e TypeScript sem emissão aprovados após sua última alteração, no A10.
Não houve alteração executável depois da suíte completa; a finalização posterior atualizou apenas relatórios/índices/planejamento.

A suíte abrange contratos, autorização cruzada, seis tools, fila, memória, quotas, leases, eventos/SSE,
migrações, rollback, replay, perda de resposta e clientes/adaptadores em transporte sintético.
Os testes dirigidos são subconjuntos desse conjunto; não somar 9 + 32 + 390 como cobertura distinta.
O teste de protocolo denominado hermes usa transporte controlado, sem comprovar runtime/LLM Hermes real.

Um aviso existente de depreciação Starlette/HTTPX permanece. Nenhuma verificação foi removida ou desabilitada.
A maior chamada individual levou 18,40 s, em test_simulation_declares_the_calls_recorded_by_the_server.
A maior preparação entre as dez fases listadas levou 14,94 s, no rollback/replay de pendência F5.
Esses números explicam parcelas do custo observado; não isolam causa de lentidão nem medem desempenho de LLM ou PostgreSQL.
As fronteiras de 300/60/30 segundos usam relógio controlado nos testes pertinentes, sem esperar os prazos inteiros.

Parecer: A0–A13 implementados/verificados no escopo local em SQLite, com fechamento técnico completo para revisão manual do responsável.
O resultado não constitui aceite global de segurança, homologação PostgreSQL ou autorização de exposição compartilhada/deploy.

## Limites de aceite

Aceite global e deploy não fazem parte desta entrega local. PostgreSQL permanece obrigatório para homologação global no bloco H.
Docker Linux não está disponível: docker info --format '{{.OSType}}' falhou com pipe dockerDesktopLinuxEngine inexistente nesta rodada.
A9 comprova disputa de admissão entre dois subprocessos em SQLite; as demais disputas locais não homologam PostgreSQL ou relógios entre hosts.
Worker/LLM Hermes/LangGraph reais, configuração/modelo remoto, rede/proxy, inspeção visual/build do portal e revisão CTO/Astra continuam pendentes.
Não houve delegação, revisão automática Astra, commit, push, PR, merge de main ou deploy. Trabalho anterior e checkout D: preservados.
Arquivos/testes executam na worktree do C:, com SQLite temporário em C:/Users/roger/AppData/Local/Temp/pytest-of-roger.
O arquivo .git da worktree ainda referencia metadados no D:; esses metadados ficaram acessíveis para as conferências Git atuais.
Relatórios antigos registram sua indisponibilidade histórica sem serem reescritos como se ela nunca tivesse ocorrido.

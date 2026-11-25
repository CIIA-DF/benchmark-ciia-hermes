# I1 — Clientes e protocolo compartilhado

Data: 31/10/2026. Worktree C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: I1 do [plano](../02-arquitetura/backend-plano-blocos.md). Sem publicação.

## Achados e correções

Uma mutação de evidência aninhada após commit alterava o corpo do retry, apesar de manter o ID lógico.
Reprodução anterior à correção: falha em 36,84 s, tmp/i1-before.log. Houve commit; o corpo seguinte já era diferente.
Também foi reproduzido retry triplo de 403 com retryable true: falha em 3,61 s, tmp/i1-revocation-before.log.

ToolClient e AsyncToolClient agora capturam cópias profundas de contexto e entrada e preparam a requisição uma vez por chamada lógica.
Retentativas reenviam os mesmos bytes, URL e cabeçalhos preparados, incluindo ID lógico, lease e chave de idempotência.
A validação da resposta usa o contexto/entrada capturados. Mutação posterior do chamador não muda a chamada em andamento.
Retentativas transitórias continuam limitadas a três, com o intervalo anterior. Nenhuma cadeia fixa ou trava global foi adicionada.
Recusas HTTP definitivas, incluindo 401/403/409, não viram retry por um sinalizador incoerente.
Retry de erro HTTP exige envelope válido, retryable true e status 408/425/429/500/502/503/504.
Falha de transporte mantém a política anterior. Sucesso inválido continua definitivo e não expõe o payload no texto da exceção.

## Workflow e contratos

Agente escolhe tool/argumentos; cliente captura contexto autenticado e prepara a entrada.
Cada chamada lógica gera um ID; cada envio HTTP corresponde a outro UUID físico do servidor.
Timeout ou perda de resposta pode coexistir com efeito confirmado. Retry conserva ID/corpo/chave e recupera o mesmo artefato.
Revogação entre commit perdido e retry produz 403 definitivo: artefato anterior continua no banco, e o cliente registra erro sem inventar recibo recebido.
Processo/inventário, busca, leitura, requisitos e recibos das duas escritas mantêm os contratos formalizados F/A.
Busca fornece documento/página à leitura e checklist fornece requisito à pendência no cenário de prova; isso não obriga sequência ou impede paralelismo.
Não houve alteração de schema, OpenAPI, assinatura pública ou formato de ExperimentRun/ToolCallRecord.
Consumidores Hermes/LangGraph usam a mesma interface; runtimes reais não foram executados.

## Evidências e depuração

```sh
uv run --locked python -m pytest tests/integration/test_i1.py tests/integration/test_adapter_protocol.py --durations=5
```

**36 casos distintos aprovados em SQLite/transportes controlados em 133,97 s**, log tmp/i1-directed.log.
Trinta próprios cobrem os dois clientes: seis contratos completos, mutação aninhada após commit perdido,
timeout, perda de resposta, armazenamento transitório, quota temporária/permanente, conflito, revogação,
403 sinalizado incorretamente, sucesso inválido, esgotamento de retries e sobreposição de chamadas no mesmo cliente.
Duas provas reais de revogação após commit verificam dois envios/um efeito e ausência de terceiro envio.
Seis regressões próximas exercitam protocolo de equipes e tratamento assíncrono anterior.

Na primeira seleção, 32 casos passaram e dois testes assíncronos falharam por lookup case-sensitive da lease no helper.
O helper foi corrigido para httpx.Headers; a seleção final inclui as provas adicionais, sem suprimir verificações.
Relógio do backend fica fixo nas provas I1 para que latência da máquina não expire a lease fora do escopo.
Backoff do cliente é substituído somente nos testes; produção conserva os intervalos anteriores.
As durações acima são de testes locais, não desempenho de agentes/LLMs. Aviso Starlette/HTTPX existente permanece.

Lint/formato dos arquivos alterados, links/invariantes e whitespace verificados.
Aceite I1: clientes equivalentes e efeitos sem duplicação, comprovado localmente.
Suíte completa reservada ao fechamento I. PostgreSQL e homologação de runtimes reais seguem pendentes no plano.
Alteração preexistente em docs/01-overview/backlog.md preservada. Sem commit, push, PR, deploy ou revisão automática CTO/Astra.

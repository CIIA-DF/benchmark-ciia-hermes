# Validação do bloco 1 — execução e acompanhamento consistentes — 25/10/2026

Trabalho local na worktree `backend-tools`, branch `team/backend`, a partir da linha de base
`bd322c9`. Escopo definido no [plano por blocos](../02-arquitetura/backend-plano-lacunas.md),
seção 6. Contratos, schema e OpenAPI permanecem inalterados.

## Comportamento entregue

- **Reconexão sem perda (A01)**: `GET /runs/{id}` lê status, resultado e cursor numa única
  consulta e limita `partial_answer` aos deltas de sequência ≤ `last_event_id`. Um delta
  confirmado durante a leitura chega pelo SSE depois do cursor. `public_run` deixou de usar
  `FOR UPDATE` e não bloqueia mais o worker no PostgreSQL.
- **Conversa coerente (A02)**: `GET /conversations/{id}` lê os runs antes das mensagens e só
  inclui a resposta do assistente quando o run está `succeeded` nesse snapshot. A mensagem e o
  status são gravados na mesma transação de `finish`.
- **Impedimento visível (A06)**: no chat, uma execução encerrada sem sucesso mostra
  `result.answer`, o motivo correspondente ao `error_code` e as fontes. O texto continua fora
  da memória da conversa.
- **Defesa na interface**: um run `succeeded` sem mensagem do assistente no snapshot exibe
  `result.answer` com as fontes.
- **Reconexão limitada**: até 4 tentativas seguidas sem receber evento, com espera de 1, 2, 4
  e 8 s. Depois disso, o chat mostra "Conexão com a execução perdida", e selecionar a conversa
  de novo retoma o acompanhamento.
- **Heartbeat após o resultado (encontrado nesta validação)**: com a máquina carregada, o
  teste de protocolo passou de 15 s e o heartbeat chegou ao servidor depois do resultado
  final. O 409 derrubava uma execução já concluída (`worker_error`). Agora heartbeat e
  resultado final são serializados em `agents.worker.execute`.

## Evidências

| Verificação | Resultado |
| --- | --- |
| `tests/backend/test_run_snapshots.py` antes da correção | A01 falhou (`'A' != 'ALOST'`); A02 falhou com a injeção antes da leitura do run |
| Mesmo arquivo depois da correção | 3 testes aprovados |
| `test_heartbeat_never_follows_final_result` antes e depois | Reproduziu o 409 no heartbeat; aprovado após a correção |
| `uv run --locked python -m scripts.dev check` | Lint, formatação, links e **54 testes aprovados em SQLite** |
| Suíte completa em PostgreSQL 17.11 (contêiner de validação isolado, `TEST_DATABASE_URL`) | **54 testes aprovados**; contêiner parado ao final |
| `scripts.export_openapi --check` e `scripts.tools_demo` | OpenAPI inalterado; seis tools, hash e replay das duas escritas verificados |
| Portal: `npm run lint`, `tsc --noEmit`, `npm run build` | Aprovados; o lint mantém o aviso antigo de `img` em `app/team/page.tsx` |
| Chromium sobre o build de produção (`data/verify_bloco1.cjs`) | Falha com motivo e fontes; resultado sem mensagem exibido; 4 reconexões com espera crescente, parada e retomada ao selecionar a conversa |
| Regressão de 25/10 (`data/verify_stream_reselection.cjs`) | Três cenários aprovados |

Os scripts de navegador ficam em `data/`, ignorado pelo Git, e usam API e EventSource
sintéticos, sem backend nem documentos reais. `data/audit_cto_probes.py` registrava os
defeitos como asserções e passa a falhar nos cenários A01 e A02. A regressão oficial agora
é `test_run_snapshots.py`.

## Limites

- A jornada no navegador simula a API; a integração real do portal com o backend foi
  exercitada só pelos testes HTTP.
- A suíte ficou lenta nesta máquina (cerca de 10 s de setup por teste) por causa da carga
  local; a primeira rodada expôs a corrida do heartbeat descrita acima.
- O Docker Desktop travou em `starting` durante a validação e precisou ser reiniciado uma vez;
  a primeira conexão logo após o reinício foi recusada e a suíte rodou em seguida.
- Agentes reais (B10) continuam fora deste bloco.

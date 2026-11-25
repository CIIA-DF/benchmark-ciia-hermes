# Exportação canônica v2 — bloco E

Data: 02/11/2026. Implementação local em `scripts.export_chat`; consumidores de Evaluation devem conferir `export_version` antes de interpretar o arquivo. Esta entrega não implementa indicadores de O, avaliação independente nem homologação de H.

## Execução e escopo

Configure `DATABASE_URL` privadamente para o banco autorizado, já migrado. O exportador é uma operação administrativa local com acesso ao banco; não aplica autenticação HTTP nem concede acesso com base nos filtros. Use diretório privado fora do Git. Ele não migra nem escreve no banco.

```powershell
uv run --locked python -m scripts.export_chat --output results/chat-v2.jsonl
uv run --locked python -m scripts.export_chat --kind benchmark --output results/benchmark-v2.jsonl
uv run --locked python -m scripts.export_chat --kind all --output results/execucoes-v2.jsonl
```

`--participant UUID`, `--conversation UUID` e `--run UUID` combinam-se por interseção. O padrão continua `--kind chat`; para exportar um run de benchmark, inclua `--kind benchmark` ou `--kind all`. Ausência de correspondências gera arquivo vazio e contagem zero. Benchmark não precisa de conversa/participante: esses campos ficam `null`.

Acrescente `--include-content` somente para incluir tarefa, resposta, mensagens, payloads dos artefatos e parâmetros livres do experimento. Sem essa opção, texto e parâmetros livres não entram no arquivo. IDs, hashes, nomes técnicos, referências e metadados continuam presentes e devem ser tratados como privados. Nunca preencher metadados com segredos. Tokens de autenticação, hashes de credenciais e lease não fazem parte da projeção, mesmo com opt-in.

## Formato JSONL

Uma linha por run, ordenada por `created_at`, `run_id`. `export_version` é a string `"2"`. Contexto e identidades de run permanecem no topo. Não há projeção reconstruída a partir de SSE.

| Campo | Origem e significado |
| --- | --- |
| `run_id`, `conversation_id`, `participant_id`, `kind`, `executor`, `context` | Identidade/contexto persistidos; participante vem da conversa por outer join |
| `declared.status`, `declared.error_code`, `declared.sources` | Resultado submetido pelo worker quando existe `result_sha256`; sem essa evidência ficam `null`, inclusive timeout produzido pelo servidor |
| `declared.experiment` | Metadados e chamadas declaradas de `ExperimentRun`, ou `null` se ausente; não é verdade metodológica |
| `declared.experiment_revisions` | Desde 21/11/2026: revisões gravadas em `/experiments` ([ADR 011](../05-decisoes/011-registro-experimental-revisoes.md)), em ordem, com `revision`, `recorded_at` e os mesmos campos de `declared.experiment`; lista vazia se o worker não usou as rotas. Quando o resultado traz `experiment`, a última revisão coincide com ele. Um run `failed` ou `timed_out` pode ter revisões com `declared.experiment` nulo (o adaptador gravou e depois falhou); nesse caso a avaliação não deve presumir que os dois coincidem |
| `observed.status`, `error_code`, timestamps | Estado persistido do run; não equivale ao estado HTTP de uma chamada |
| `observed.latency_ms` | Diferença entre `finished_at` e `started_at`, vezes 1.000; `null` se faltar um extremo. Relógio de parede pode sofrer ajustes; não soma durações de tools paralelas |
| `observed.task_metadata` | `task_id`, `split`, `repetition` registrados pelo servidor |
| `observed.logical_calls` | Linhas de `logical_tool_calls`: `run_id`, `tool_call_id`, `tool`, `args_sha256`; ordenadas pelo ID lógico |
| `observed.physical_attempts` | Linhas de `physical_tool_attempts` com suas `phases`; ordenadas por início/UUID. Inclui falhas posteriores ao encerramento do run |
| `observed.legacy_tool_stages` | Linhas de `tool_calls`, preservadas por ID lógico/número da etapa; não são novas requisições físicas |
| `observed.artifacts` | ID, run, ferramenta, chave de idempotência, hash da entrada e recibo armazenado; ordenados pelo ID. O payload só aparece no opt-in |
| `evaluated.verified_success`, `evaluated.evaluator` | `null`: não há fonte de avaliação independente nas tabelas consultadas; não copiar alegação do agente para essa seção |
| `history_precision` | Fonte `persisted_history`, legado `stages_not_physical_requests`, total de requisições desconhecido e exclusão explícita de tentativas sem run atribuível |
| `content` | Presente apenas com opt-in; artefatos incluem ID junto ao payload para associação segura |

`declared.experiment` preserva versão do registro, IDs/contexto, tarefa/split/repetição/executor, versões de código/harness/adaptador, modelo/endpoint, hash do prompt, início/latência declarados, chamadas, tokens/custo, sucesso declarado e IDs de artefatos declarados. `parameters` só aparece em `content.parameters` (e, por revisão, em `content.revision_parameters`). Por isso a contagem `unobserved_tool_calls` (P10, chamadas que nunca chegaram ao servidor) só sai com `--include-content`; levar o campo para `declared` é decisão do bloco O. Valores opcionais ausentes permanecem `null`; zeros realmente registrados continuam zero. A versão interna `ExperimentRun.contract_version=0.1` não muda.

As tentativas físicas incluem UUID, método, ferramenta, run/ID lógico/hash atribuídos, início/fim, `response_state`, `http_status`, `code`, `client_received` e fases. Cada fase conserva nome, timestamp, artefato e replay. Ordem das fases é semântica: início, efeito e conclusão/falha/interrupção; não depende de relógios monotônicos.

`http_status` representa resposta preparada; `client_received=null` não confirma entrega nem significa falha. Em coleta final perdida, fim/status podem permanecer `null` mesmo com efeito confirmado. Um recibo persistido não é prova de sucesso metodológico. A exportação não recalcula sustentação de evidências nem substitui a validação de integridade pelo GET de artefatos.

## Legado, lacunas e contagens

Uma chamada lógica pode ter diversas tentativas físicas e um único artefato. Uma tentativa pode ter várias fases. O ledger legado pode registrar duas etapas para uma única requisição com falha pós-commit. Portanto, não somar linhas legadas, fases e tentativas como uma só unidade.

Contar `observed.physical_attempts` fornece a quantidade de registros físicos atribuídos presentes naquele snapshot. Não fornece a quantidade total de requisições que chegaram à API: antes de 0006, em falha de coleta inicial e em requisições sem atribuição não existe essa prova. Por isso `history_precision.total_physical_requests` permanece `null`, inclusive quando a lista física está vazia. Não há backfill inferido nem correspondência artificial entre etapas legadas e UUIDs físicos.

Tentativas com `run_id=null` não são anexadas arbitrariamente a nenhum run, inclusive com `--kind all`; `unattributed_attempts_included=false` declara essa limitação. Exportação global de tráfego anônimo não faz parte deste formato por execução.

Falhas tardias são selecionadas pelo `run_id`, sem corte pelo `finished_at` e sem depender de evento SSE. Declaração aceita anteriormente permanece intacta, embora novas tentativas observadas possam aparecer numa exportação posterior.

## Snapshot e publicação do arquivo

O exportador abre um snapshot de leitura para o arquivo inteiro. SQLite recebe `BEGIN` explícito, pois o modo legado do driver não inicia transação para SELECT; PostgreSQL usa `REPEATABLE READ`. Escritas posteriores ao snapshot não são misturadas às tabelas já lidas. Runs ativos continuam sendo fotografias parciais; nova exportação pode conter novos registros.

Grava primeiro um temporário no diretório de destino, fecha e sincroniza os bytes, depois publica por hard link exclusivo. Nunca sobrescreve destino existente, inclusive em disputa. Falha tratada de SQL, serialização ou publicação remove o temporário e não publica arquivo final parcial. O volume deve permitir hard links; não há fallback para sobrescrita. Desligamento abrupto pode deixar `.export-*.tmp` privado, que não deve ser consumido. Isso não substitui backup/restauração ou garantia contra perda de energia.

Contextos, recibos e registros experimentais devem aderir aos modelos; corrupção estrutural interrompe a exportação. Erro de CLI não imprime SQL nem conteúdo rejeitado. Bases anteriores devem ser atualizadas pelo fluxo de migração existente antes da exportação; este comando não faz migração automática.

## Migração do consumidor v1

| v1 | v2 |
| --- | --- |
| `tool_calls` reconstruído de eventos | `observed.physical_attempts` para requisições; `observed.logical_calls` para vínculos; `declared.experiment.tool_calls` para relato |
| `receipts` | `observed.artifacts[].receipt` |
| Estado, timestamps e latência no topo | `observed` |
| Tokens/custo/modelo no topo | `declared.experiment`, ou `null` quando não há registro experimental |
| `sources` no topo | `declared.sources` |
| Payloads sem associação explícita em `content.artifacts` | Lista de objetos `{artifact_id, payload}` |

Arquivos v1 existentes não são reescritos. Não oferecer aparência de precisão física a um arquivo v1: conservar sua versão ou reexportar da base migrada, mantendo a identificação do legado. API HTTP e sua versão `0.3.0` não mudam; não há nova migração, dependência ou alteração de tool/identidade/proxy neste bloco.

## Conferência independente

[Testes E](../../tests/backend/test_e_export.py) exportam JSONL e consultam SQL diretamente para confrontar conjuntos de IDs, todas as colunas de chamadas/tentativas, fases, hashes, recibos e artefatos. Não usam o leitor do exportador para montar o resultado esperado. Exercitam falha pós-commit/retry, rollback, chamada tardia sem SSE, conclusão desconhecida, legado puro/misto, filtros, snapshot concorrente e falha de publicação.

[Relatório E](validacao-e.md) registra comandos, resultados e limites. Metodologia e equipes consumidoras precisam revisar a mudança de versão antes de incorporar os arquivos. PostgreSQL e homologação global permanecem no bloco H; indicadores, denominadores e inferências pertencem a O.

# Integração das equipes Hermes e LangGraph

## Entrega do Backend

As seis tools e seus contratos estão em [contratos](../../contracts/README.md).
`contracts.catalog.tool_catalog()` devolve nome, descrição e parameters JSON Schema.
As equipes traduzem esse formato para o runtime oficial adotado; não se presume
compatibilidade direta com um protocolo específico de LLM.

Implementar o protocolo [AgentAdapter](../../agents/interface.py):
`stream(ClaimedRun, AsyncToolClient)` produz AgentEvent e termina com AgentResult.
History já contém a pergunta atual; não adicioná-la novamente. Falhas e parciais
não são memória da pergunta seguinte. Credenciais e marcador de participante
não entram no prompt.

### Erros das tools (desde 25/10/2026)

`AsyncToolClient.call` (e `ToolClient.call`) separa dois casos:

- Corrigível pelo modelo (`validation_error`, `not_found`, `idempotency_conflict`):
  devolve `{"error": {"code", "message", "run_id", "retryable"}}` sem lançar exceção.
  Entregue esse dict ao modelo como resultado da tool para que ele corrija os
  argumentos ou declare o impedimento. Não trate como evidência de ausência.
- Definitivo (401, 403, reserva expirada, `version_mismatch`, `budget_exceeded`, 5xx ou
  corpo fora do contrato): lança `agents.interface.ToolCallError`, subclasse de
  `httpx.HTTPStatusError`, com `.error` (`ToolError` ou `None`). O modelo não
  resolve esses casos; encerre a execução. Para `budget_exceeded`, termine com
  `AgentResult(status="failed")` e declare o limite.

Antes dessa data, qualquer status 4xx/5xx lançava `HTTPStatusError`.

### Rastreio, novas tentativas e orçamento (v0.3)

- O cliente gera um `tool_call_id` por chamada lógica e o envia em `X-Tool-Call-Id`.
  O backend registra cada tentativa sob esse ID.
- Falhas transitórias (`retryable: true`, como 503 `storage_unavailable`, ou erro de
  transporte) são repetidas pelo próprio cliente até 3 vezes, com o mesmo corpo e o mesmo
  ID; escritas repetem a mesma `idempotency_key`. Não reimplemente essa política no
  adaptador, para que os dois executores tenham o mesmo comportamento.
- `tools.calls` acumula um `ToolCallRecord` por chamada lógica (ID, tool, duração total,
  `ok`/`error`, `artifact_id`). Use `list(tools.calls)` em `ExperimentRun.tool_calls`; o
  simulador já faz isso. Esse é o registro declarado pelo adaptador; o histórico do
  servidor é a referência para conferência.
- Desde 25/11/2026 (P10): uma chamada lógica cujas tentativas falharam todas antes do envio
  (`httpx.ConnectError`, `ConnectTimeout`, `PoolTimeout`) nunca chega ao servidor e vai para
  `tools.unobserved`, não para `tools.calls`. Grave a quantidade em
  `ExperimentRun.parameters["unobserved_tool_calls"]` (inteiro ≥ 0, não decrescente entre
  revisões); a `RunBridge`, o `ExperimentSink` e o simulador já fazem isso, inclusive com 0.
  Assim um run em que o agente se recupera da queda não é mais recusado no `/result`. Falha
  possivelmente enviada (por exemplo `ReadTimeout`) continua em `tools.calls` como `error`.
- `RUN_MAX_TOOL_CALLS` limita as chamadas lógicas por execução no servidor, igual para
  Hermes e LangGraph. Novas tentativas do mesmo ID não consomem orçamento.

## Inicialização

A equipe entrega uma fábrica Python sem argumentos que retorna seu adaptador.
Configuração de modelo vem do ambiente privado. Exemplo de comando, substituindo
MODULO_REAL:FABRICA_REAL pela implementação efetivamente entregue:

```powershell
uv run --locked python -m agents.worker --executor hermes --adapter MODULO_REAL:FABRICA_REAL
uv run --locked python -m agents.worker --executor langgraph --adapter MODULO_REAL:FABRICA_REAL
```

Não são nomes de APIs do Hermes. O backend não instala runtimes automaticamente.
Provisionar identidade do worker com executor e concessões por processo/corpus,
conforme [chat](chat.md). Configurar BACKEND_URL e BACKEND_WORKER_TOKEN privadamente.
Habilitar o executor no backend com ENABLED_EXECUTORS somente no ambiente de
homologação preparado. A disponibilidade anunciada é configuração, não prova
de saúde de um worker.

Para testar protocolo sem inferência:
`uv run --locked python -m agents.worker --executor simulation`.
Não registrar o simulador sob o nome de outro executor.

### Ponte para adaptadores `run()` da v0.1 (desde 21/11/2026)

Hermes (`team/hermes`), LangGraph (`task/langgraph-grafo`) e o runner da Evaluation
implementam `run(task, context) -> ExperimentRun` com cliente síncrono. Para não exigir a
reescrita em `stream()` antes de 15/12, [agents/compat.py](../../agents/compat.py) oferece
`RunBridge`, que embrulha esse formato como `AgentAdapter`:

```python
# Fábrica sem argumentos entregue pela equipe, usada em --adapter modulo:funcao.
from agents.compat import RunBridge


def adapter():
    return RunBridge(lambda tools, execution: MeuAdaptador(tool_client=tools))
```

- A fábrica interna recebe um `SyncToolClient` (`call(name, arguments) -> dict`) e o
  `ClaimedRun`, e cria o adaptador por execução. O cliente delega ao `AsyncToolClient` do
  worker: mesmo token de reserva, `X-Tool-Call-Id`, novas tentativas e tradução de erros
  descritos acima. O contexto da execução é injetado pelo servidor; não reutilize clientes
  `ToolClient(base_url)` próprios.
- O adaptador precisa aceitar o cliente injetado. O LangGraph já recebe `tool_client` no
  construtor. O Hermes atual cria `ToolClient(backend_url)` dentro de `run()`; a equipe
  precisa expor um parâmetro equivalente antes de usar a ponte.
- Resposta: `run_with_result()` (resposta e registro), quando existir; senão `run()` e o
  atributo `final_response`. O texto sai inteiro ao final, em deltas de até 4000 caracteres.
- Em `benchmark`, o `ExperimentRun` precisa ter o mesmo `run_id`, processo, versões,
  tarefa, divisão, repetição e executor da reserva; divergência vira
  `AgentResult(status="failed", error_code="adapter_error")`. `tool_calls` é substituído
  pelo registro do cliente comum, igual para os dois executores, e `persisted_artifact_ids`
  pelos artefatos dessas chamadas; a conferência continua pelo histórico do servidor.
- Exceção no `run()` vira resultado terminal: `model_timeout` para timeout HTTP do modelo,
  `adapter_error` nos demais casos.
- Limites: sem eventos parciais nem streaming de raciocínio; a thread do `run()` não é
  interrompida, e o prazo continua sendo o da reserva no servidor. A migração nativa para
  `stream()` continua recomendada para o chat.

#### `ExperimentSink` para o LangGraph

O adaptador do LangGraph (`task/langgraph-grafo`, `856ff06`) grava o `ExperimentRun` por um
`sink` (`save`/`get`/`update`). Uma fábrica de três argumentos recebe o `ExperimentSink`, que
grava nas rotas `/experiments` com o token e a reserva do worker
([ADR 011](../05-decisoes/011-registro-experimental-revisoes.md)):

```python
from agents.compat import RunBridge, task_fields


def adapter():
    return RunBridge(
        lambda tools, sink, execution: LangGraphAdapter.from_environment(
            model_factory=FABRICA_DO_PROVEDOR,
            tool_client=tools,
            sink=sink,
            metadata=RunMetadata(**task_fields(execution), **VERSOES_DA_EQUIPE),
        )
    )
```

`FABRICA_DO_PROVEDOR` e `VERSOES_DA_EQUIPE` (`code_commit`, `harness_version`,
`adapter_version`, `endpoint_id`) são da equipe LangGraph; o backend não os define.

- Antes de gravar, o sink troca `tool_calls` e `persisted_artifact_ids` pelos do cliente comum.
  Os IDs `tool-<hex>` do `RecordingToolClient` não chegam ao servidor.
- Em benchmark, a última revisão gravada vira o `experiment` do resultado. Se houver chamada de
  tool depois dela, a ponte encerra com `adapter_error`: grave uma revisão nova antes de terminar.
- O `ExperimentRun` devolvido por `run()`/`run_with_result()` precisa ser igual à última revisão
  gravada (sem `parameters.revision` conta como 1). Se diferir, por exemplo latência ou tokens
  atualizados depois do último `save`/`update`, a ponte encerra com `adapter_error` em vez de
  descartar o relatório final; a ponte não grava revisões no lugar do adaptador. O LangGraph do
  `856ff06` já devolve o registro que acabou de gravar.
- Em chat, o sink guarda a revisão só em memória; o servidor não registra experimento de chat.
- Quem usa `ExperimentRunClient` diretamente passa `token=` e `run_token=`; sem eles, 401.

Evidência: `tests/backend/test_compat.py` e `tests/backend/test_experiment_runs.py`
(adaptadores falsos sobre worker e backend reais em SQLite). Isso não homologa Hermes nem
LangGraph reais.

#### Catálogo único de tools (proposta de 22/11/2026)

Em 22/11/2026, cada executor descreve as tools para o modelo de um jeito: o Hermes
(`team/hermes`, `agents/hermes/tools.py`) envia as seis com descrições próprias; o LangGraph
(`task/langgraph-grafo`, `make_backend_tools`) expõe três, também com descrições próprias.
Isso muda o prompt de cada executor e compromete a comparação. Proposta para as duas equipes
e para a Metodologia, sem alterar o contrato HTTP:

- enviar ao modelo `contracts.catalog.openai_tools()`, que é o `tool_catalog()` no formato de
  function calling (`{"type": "function", "function": {...}}`), aceito por `/chat/completions`
  e por `bind_tools` do LangChain;
- registrar `contracts.catalog.catalog_version()` (SHA-256 do catálogo em JSON canônico) em
  `ExperimentRun.parameters["catalog_version"]` e congelar a versão antes da coleta.

Valor em 25/11/2026, depois do P3 (que acrescentou o pattern sem U+0000 a `content` e
`evidence_note`): `f419b756f28a47ace8f413ddc7204c66f9e30059991ba8e9b664d05100e77e2c`. O valor
calculado sobre `d879efb` (22/11) não vale mais. Qualquer mudança nos schemas de entrada das tools
muda a versão; recalcule com `python -c "from contracts.catalog import catalog_version;
print(catalog_version())"` antes de congelar.

A rota `GET /capabilities` não publica a versão: acrescentar o campo muda uma resposta com
campos extras proibidos e depende de revisão das equipes. Evidência:
`tests/backend/test_catalog_shared.py`.

### Rodada do benchmark (Hermes × LangGraph)

1. Provisione um worker por executor (`worker-hermes`, `worker-langgraph`), cada um com seu
   token em variável privada, `executor`, `can_write` e as concessões do corpus da rodada
   (`scripts.provision`, ver [chat](chat.md)). Para revogar, use `--operation update` com
   concessões vazias; para trocar só o token, `--operation rotate`.
2. Habilite `ENABLED_EXECUTORS=hermes,langgraph` e use o mesmo `LLM_BASE_URL`, `LLM_MODEL` e
   parâmetros nos dois workers (ADR 003).
3. Defina `RUN_MAX_TOOL_CALLS` com a Metodologia antes da coleta; `0` deixa sem limite.
4. Confira `GET /ready` (schema na revisão esperada) antes de enfileirar.
5. Enfileire com `scripts.benchmark_batch` usando um rótulo fixo por rodada, por exemplo:
   `uv run --locked python -m scripts.benchmark_batch evaluation/tasks.json --label camada1-dev --executor hermes --executor langgraph --repetitions 5 > manifesto.jsonl`.
   A ordem é contrabalançada (cada executor vai primeiro na metade dos pares, com `position` no
   manifesto), como pede o protocolo da Metodologia. O lote tolera um reinício do backend: repete
   erro de transporte e 503 `retryable`. Só desiste quando nada avança por `--stall-seconds`, e
   nesse caso lista os itens restantes como `not_submitted`. Para retomar, rode o mesmo comando
   com o mesmo rótulo: os runs já criados são reaproveitados.
6. Exporte com `scripts.export_chat --kind benchmark` para a avaliação.

## Checklist de homologação por equipe

- Registrar origem/licença/versão do runtime, factory, commit e dependências fixadas.
- Configurar o mesmo modelo/endpoint, corpus, requisitos e limites comparáveis.
- Executar consulta com referência verificável e continuação de conversa.
- Executar pendência e minuta; conferir artefatos e hashes como operador independente.
- Demonstrar busca vazia/cobertura parcial sem inventar ausência.
- Repetir escrita após perda simulada da resposta, mantendo chave e conteúdo.
- Demonstrar parada por limite, erro temporário e retomada do acompanhamento SSE.
- Benchmark: fornecer ExperimentRun coerente; sucesso verificado e avaliador
  permanecem null para preenchimento pela Metodologia.

Registrar comandos, IDs, versões e resultados observados em armazenamento privado.
Não registrar prompts/documentos/chaves nos logs operacionais.
Nenhum adaptador real foi incluído nesta entrega do Backend; homologação depende
das equipes, sem substituir esse aceite por um teste de simulação.

## I1 — requisição estável por chamada

Clientes síncrono/assíncrono capturam contexto, argumentos aninhados e bytes/cabeçalhos antes do primeiro envio.
Retry mantém ID, corpo, chave e lease; mutação posterior do chamador não muda a chamada em curso.
Erro HTTP transitório exige envelope retryable e status transitório; 401/403/409 continuam definitivos mesmo com sinalizador incoerente.
Sucesso inválido não recebe retry automático. Chamadas independentes podem se sobrepor; nenhum workflow fixo foi imposto.
[Evidências e limites I1](validacao-i1.md).

## I2 — rotação e reinício

Token antigo não volta a valer ao reiniciar com ambiente antigo. Bootstrap não atualiza perfis existentes.
Use scripts.provision FILE --operation rotate com principal_id/token_env para preservar direitos; atualize os segredos privados dos clientes autorizados.
Rotação durante uma escrita pode produzir 403 sem efeito novo; novas chamadas com segredo antigo recebem 401.
[Evidências e operação I2](validacao-i2.md).

## I3 — Transporte e homologação

ModelConfig rejeita timeout não positivo ou não finito. Falhas controladas do proxy cobrem limites, cursores SSE, cabeçalhos e cancelamento upstream.
O proxy do portal não é o cliente de tools e não encaminha credencial de worker do navegador.
Testes locais não comprovam Nginx/Compose ou inferência real. [Configuração, catálogo e evidências I3](validacao-i3.md).

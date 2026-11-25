# Validação K — Hermes, LangGraph e Evaluation sobre o backend v0.2

Data: 22/11/2026. Worktree `team/backend`, HEAD `d879efb` (blocos I, E, J, S1 e D em commits locais, mais o catálogo comum). As branches das outras equipes não foram alteradas: cada conferência rodou numa worktree temporária com o HEAD do backend e só as pastas da equipe copiadas da branch remota. Worktrees, venv e arquivos de apoio ficaram no diretório temporário da sessão, fora do repositório.

## Resumo

| Frente | Branch / commit | Resultado sobre a v0.2 | O que falta |
| --- | --- | --- | --- |
| Hermes (Hugo) | `team/hermes` `06e16bb` | Na própria branch: 32/32. Sobre a v0.2: 16 falhas, todas `TypeError` de `ToolClient(backend_url)` (assinatura v0.1). Com o patch proposto, o adaptador roda pela `RunBridge` com LLM falso (2/2 testes novos) | Patch do adaptador e do helper dos testes; catálogo comum |
| LangGraph (João Enomoto) | `task/langgraph-grafo` `856ff06` | 9/9 testes do João e 1/1 ponta a ponta (`RunBridge` + `ExperimentSink` + `/experiments`), com modelo falso | PR sem o backend v0.1; usar as 6 tools pelo catálogo comum |
| Evaluation | `team/evaluation` `7d7b45a` | 16/16 sobre a v0.2, iguais à branch | Métricas leem `ExperimentRun` por arquivo, não o JSONL v2 |
| Evaluation (piloto) | `task/evaluation-tasks-piloto` `e515376` | 67/71. As 2 falhas da própria branch (arquivos secretos ignorados pelo Git, ausentes num checkout limpo) mais 2 que só existem na combinação: `.gitignore` sem `test_set_secret` e hash do `uv.lock` no `freeze_manifest.json` | Regerar o manifesto depois do merge; nenhuma incompatibilidade de contrato |

Nenhum teste usou LLM real, OpenRouter, PostgreSQL ou rede. Isso não homologa Hermes nem LangGraph.

## Catálogo de tools enviado ao modelo

Os dois executores enviam ao modelo catálogos diferentes do backend:

- Hermes: as seis tools, com descrições próprias em `agents/hermes/tools.py`. As seis descrições diferem de `contracts.catalog.openai_tools()`.
- LangGraph: só `consultar_processo`, `buscar_documentos` e `ler_documento`, com descrições próprias em `make_backend_tools`. O corte para três vem da v0.1, quando as escritas davam 501.

Com isso, Hermes e LangGraph recebem prompts diferentes, e a comparação perde validade. O commit `d879efb` acrescenta `openai_tools()` e `catalog_version()` ([integração](integracao-agentes.md#catálogo-único-de-tools-proposta-de-22112026)). Adotar esse catálogo e congelar a versão antes da coleta depende das duas equipes e da Metodologia.

## Hermes

**Incompatibilidades com a v0.2**

1. `HermesAdapter.run()` cria `ToolClient(backend_url)`. Na v0.2, o `ToolClient` exige token, contexto e reserva, e a `RunBridge` entrega um cliente pronto; sem injeção, o run termina `failed` com `adapter_error` (teste `test_unpatched_hermes_cannot_build_v02_tool_client`).
2. `task_id`, `split` e `repetition` vêm de argumentos com padrão (`development`, 1). A ponte chama `run(task, context)` e confere o registro com a reserva: repetição 2 em diante divergiria.
3. O helper `_mock_openai_client` dos testes também cria `ToolClient(base_url)`; por isso 16 testes falham na v0.2 mesmo com o patch.
4. `ToolCallError` herda de `httpx.HTTPStatusError`; o adaptador a trata como erro de tool e continua o loop, inclusive em falhas definitivas (401, 403, 409 de reserva). O run termina pelo prazo da reserva, não pelo erro. Recomendação ao Hugo, não testada aqui.

**Patch proposto (44 linhas, só `agents/hermes/adapter.py`, mais `agents/hermes/bridge.py`)**

- `HermesAdapter(tool_client=None, metadata=None)`. `run()` usa o cliente injetado quando houver e mantém `ToolClient(backend_url)` como padrão.
- A assinatura de `run()` não muda. Quando `metadata` vem da reserva (`agents.compat.task_fields`), `task_id`, `split` e `repetition` dela prevalecem.
- `agents/hermes/bridge.py`: `adapter()` devolve `RunBridge(lambda tools, execution: HermesAdapter(tool_client=tools, metadata=task_fields(execution)))`, para `agents.worker --executor hermes --adapter agents.hermes.bridge:adapter`.

Arquivos para a equipe aplicar e revisar na própria branch (`git apply`, conferido com `git apply --check`): [hermes-runbridge.patch](validacao-k/hermes-runbridge.patch), sobre `team/hermes` `06e16bb`, com o adaptador, a fábrica e os dois testes novos; [langgraph-runbridge-test.patch](validacao-k/langgraph-runbridge-test.patch), sobre `856ff06`, só com o teste ponta a ponta. Os testes dependem do backend v0.2 (`agents.compat`, `tests/backend/test_compat.py`), então só passam depois do merge com a `team/backend`.

**Comandos e resultados**

| Verificação | Resultado |
| --- | --- |
| `pytest tests/hermes` na `team/hermes` | 32 aprovados |
| Mesmo comando sobre a v0.2, sem patch | 16 aprovados, 16 falhas (`TypeError` em `ToolClient`) |
| Sobre a v0.2, com patch e 2 testes novos (`test_bridge_v02.py`) | 18 aprovados; as mesmas 16 falhas do helper dos testes |
| `test_patched_hermes_runs_through_bridge_with_reservation_metadata` | Worker `hermes`, reserva com repetição 2, duas tools (uma `not_found` corrigível), resultado `succeeded`; `ExperimentRun` com executor, tarefa, divisão, repetição, chamadas e tokens (20/10) conferidos pelo servidor |

## LangGraph

| Verificação | Resultado |
| --- | --- |
| `tests/test_langgraph_adapter.py` e `tests/test_langgraph_graph.py` do `856ff06`, sobre a v0.2, venv temporário com langgraph 1.2.18, langchain-core 1.7.1 e langgraph-checkpoint-sqlite 3.1.3 | 9 aprovados |
| Ponta a ponta: `LangGraphAdapter` com modelo falso pela `RunBridge`, `ExperimentSink`, worker `langgraph` e repetição 3 | Aprovado; a última revisão em `/experiments/{run_id}/revisions` é igual ao `experiment` do resultado |

`git merge-tree` do `856ff06` sobre o HEAD do backend aponta conflito em `agents/README.md`, `agents/interface.py`, `agents/smoke.py`, `contracts/README.md`, `evaluation/protocol.md`, `services/backend/README.md`, `services/backend/app.py`, `tests/backend/test_experiment_runs.py` e `uv.lock`. O backend da branch é o v0.1 já portado no bloco J ([ADR 011](../05-decisoes/011-registro-experimental-revisoes.md)); o PR do LangGraph para `main` deveria levar só `agents/langgraph/`, os testes do adaptador e as dependências.

## Evaluation

- `evaluation/metrics.py` lê um arquivo JSON de `ExperimentRun` por execução (`model_validate_json`). A [exportação canônica](exportacao-canonica.md) gera JSONL v2 com `declared.experiment` em campos selecionados e `parameters` só com `--include-content`. Falta um caminho documentado entre os dois: exportar `ExperimentRun` por run ou ler o JSONL v2 nas métricas. A decisão é da Metodologia com o Backend.
- `freeze_manifest.json` fixa o SHA-256 do `uv.lock`. Qualquer merge com o backend (S1 mudou o lock) exige regerar o manifesto.
- `git merge-tree` aponta conflito textual em `.env.example`, `docs/05-decisoes/README.md` e `evaluation/README.md` (`team/evaluation`) e em `evaluation/protocol.md` (piloto).

## Não verificado

- Hermes e LangGraph com LLM real, OpenRouter ou qualquer rede externa.
- PostgreSQL nessas conferências (só SQLite).
- O patch do Hermes não foi aplicado na branch do Hugo; o tratamento de falhas definitivas (item 4) não foi testado.
- Revisões das equipes Hermes, LangGraph e Metodologia.

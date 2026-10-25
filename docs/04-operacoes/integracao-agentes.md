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
- Definitivo (401, 403, reserva expirada, `version_mismatch`, 5xx ou corpo fora do
  contrato): lança `agents.interface.ToolCallError`, subclasse de
  `httpx.HTTPStatusError`, com `.error` (`ToolError` ou `None`). O modelo não
  resolve esses casos; encerre a execução ou aplique a política de retentativa
  da equipe quando `error.retryable` for verdadeiro, repetindo escritas com a
  mesma `idempotency_key`.

Antes dessa data, qualquer status 4xx/5xx lançava `HTTPStatusError`.

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

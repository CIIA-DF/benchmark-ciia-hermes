# Integração compartilhada dos agentes

Backend oferece [AgentAdapter e clientes HTTP](interface.py),
[catálogo público](../contracts/catalog.py) e [worker](worker.py).
O worker carrega uma fábrica local explicitamente fornecida pela equipe:

```powershell
uv run --locked python -m agents.worker --executor simulation
```

Para Hermes/LangGraph, seguir o [handoff](../docs/04-operacoes/integracao-agentes.md).
Não há adaptadores reais implementados neste diretório. O simulador é identificado
como tal e não chama LLM. Smoke e dublês de teste validam HTTP/protocolo, não inferência.

O cliente injeta o contexto autenticado, limita o catálogo e não repete escritas
com chave nova. Modelo não recebe credenciais. Configuração privada de inferência:
LLM_BASE_URL, LLM_MODEL, LLM_API_KEY e LLM_TIMEOUT_SECONDS.

[Contratos](../contracts/README.md) · [Hermes](hermes/README.md) · [LangGraph](langgraph/README.md).

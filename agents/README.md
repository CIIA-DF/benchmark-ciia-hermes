# Interfaces dos agentes

[interface.py](interface.py) define AgentAdapter, ModelConfig e ToolClient compartilhados. [smoke.py](smoke.py) testa apenas comunicação HTTP com backend populado; [Hermes](hermes/README.md) inclui a integração experimental com endpoint OpenAI-compatible.

```sh
uv run --locked python -m agents.smoke --adapter hermes
uv run --locked python -m agents.smoke --adapter langgraph
```

Antes: execute demo e deixe serve rodando em outro terminal. BACKEND_URL permite escolher endpoint para o smoke. O adaptador Hermes lê LLM_BASE_URL, LLM_MODEL, LLM_API_KEY e LLM_TIMEOUT_SECONDS; o smoke não lê chave. O cliente usa timeout explícito, allowlist de ferramentas e propaga erros HTTP; não faz retry de escrita automaticamente.

[Hermes](hermes/README.md) · [LangGraph](langgraph/README.md). Hermes executa o loop ReAct experimental; integração ao harness, avaliação e persistência de ExperimentRun continuam pendentes. O smoke não executa agente ou LLM.

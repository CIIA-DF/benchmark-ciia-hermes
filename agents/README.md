# Interfaces dos agentes

[interface.py](interface.py) define AgentAdapter, ModelConfig e ToolClient compartilhados. [smoke.py](smoke.py) testa apenas comunicação HTTP com backend populado, sem modelo ou executor.

```sh
uv run --locked python -m agents.smoke --adapter hermes
uv run --locked python -m agents.smoke --adapter langgraph
```

Antes: execute demo e deixe serve rodando em outro terminal. BACKEND_URL permite escolher endpoint. LLM_BASE_URL, LLM_MODEL, LLM_API_KEY e LLM_TIMEOUT_SECONDS são configuração reservada à integração real; o smoke não lê chave. O cliente usa timeout explícito, allowlist de ferramentas e propaga erros HTTP; não faz retry de escrita automaticamente.

[Hermes](hermes/README.md) · [LangGraph](langgraph/README.md). Integração real e coleta de ExperimentRun estão pendentes; não apresentar smoke como agente funcionando.

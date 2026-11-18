# Interfaces dos agentes

[interface.py](interface.py) define AgentAdapter, ModelConfig, ToolClient e o cliente de registros compartilhados. [smoke.py](smoke.py) testa apenas comunicação HTTP com backend populado, sem modelo ou executor.

```sh
uv run --locked python -m agents.smoke --adapter hermes
uv run --locked python -m agents.smoke --adapter langgraph
```

Antes: execute demo e deixe serve rodando em outro terminal. BACKEND_URL permite escolher endpoint. `LangGraphAdapter.from_environment` lê LLM_BASE_URL, LLM_MODEL, LLM_API_KEY e LLM_TIMEOUT_SECONDS e recebe uma `model_factory` específica do provedor; o projeto não fixa provedor/protocolo até essa decisão ser validada. O smoke não lê chave. Clientes HTTP usam timeout explícito e propagam erros; o cliente de ferramentas só libera as três operações de leitura implementadas.

[Hermes](hermes/README.md) · [LangGraph](langgraph/README.md). O adaptador LangGraph executa com ChatModel e backend injetados e persiste `ExperimentRun`; o smoke permanece apenas um teste HTTP. Hermes e coleta experimental comparativa ainda dependem da integração correspondente.

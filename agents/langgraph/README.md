# LangGraph — integração planejada

LangGraph ainda não é dependência instalada. Versão será escolhida/registrada antes da implementação real. A interface comum está em [AgentAdapter/ToolClient](../interface.py).

Ciclo previsto: tarefa e estado chegam ao modelo; o modelo pode solicitar uma ou mais ferramentas; o adaptador valida o nome e envia a chamada ao backend; o resultado/erro retorna ao estado e ao modelo; o próximo passo pode ser outra chamada ou encerramento. Limites de chamadas, tempo e tokens devem interromper execução com motivo registrado.

Nós/arestas controlam transições; não fixam uma sequência de ferramentas que já solucione o benchmark. Estado, mensagens, tratamento de erro e checkpoints precisam ser definidos para permitir comparação com Hermes. Não há inferência, persistência de checkpoint ou agente completo hoje.

Com API populada em execução: `uv run --locked python -m agents.smoke --adapter langgraph`. Isso testa apenas HTTP. [Guia da equipe](../../docs/03-equipes/langgraph.md) e [quickstart oficial consultado](https://docs.langchain.com/oss/python/langgraph/quickstart).

# Hermes — adaptador experimental

O pacote/runtime Hermes oficial não foi instalado ou confirmado por este projeto. A coordenação ainda deve confirmar URL, versão/commit, licença e identidade do executor; o adaptador usa diretamente o protocolo HTTP OpenAI-compatible solicitado, sem presumir capacidades de um pacote Hermes.

Ponto de entrada comum: [AgentAdapter, ModelConfig e ToolClient](../interface.py). [adapter.py](adapter.py) implementa um loop ReAct mínimo com endpoint OpenAI-compatible e as ferramentas de leitura. `HermesAdapter.run` exige `LLM_BASE_URL`, `LLM_MODEL` e `LLM_API_KEY`, além da API populada em `http://127.0.0.1:8000`. O smoke `uv run --locked python -m agents.smoke --adapter hermes` continua verificando somente HTTP; não integra a LLM.

Próxima etapa: registrar identidade em ADR, verificar documentação oficial e mapear seleção/chamada de ferramentas, estado, encerramento e logs ao contrato comum. Não inventar nomes de métodos ou capacidades. [Guia da equipe](../../docs/03-equipes/hermes.md).

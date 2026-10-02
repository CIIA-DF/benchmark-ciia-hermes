# Hermes — identidade pendente

Não há pacote Hermes instalado por este projeto. A coordenação deve confirmar URL oficial, versão/commit, licença, API de extensão e configuração de modelo. Software de nome semelhante já instalado na máquina não é evidência de que seja o executor escolhido.

Ponto de entrada comum: [AgentAdapter e ToolClient](../interface.py). Com API populada em execução, `uv run --locked python -m agents.smoke --adapter hermes` verifica somente HTTP. Não integra Hermes nem chama LLM.

Próxima etapa: registrar identidade em ADR, verificar documentação oficial e mapear seleção/chamada de ferramentas, estado, encerramento e logs ao contrato comum. Não inventar nomes de métodos ou capacidades. [Guia da equipe](../../docs/teams/hermes.md).

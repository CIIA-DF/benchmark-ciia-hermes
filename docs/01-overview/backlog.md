# Backlog inicial versionado

Estado inicial de todos os itens abaixo: **aberto**. Responsável/revisor: preencher nos [guias](teams/README.md). Não foram publicadas issues remotas. Converta em issues pequenas conforme a capacidade, mantendo ligação com este documento.

A base de integração já entregue é a demo sintética; as tarefas abaixo começam conferindo essa base antes de ampliá-la.

| Equipe / ID | Tarefa pequena | Dependência | Aceite verificável |
| --- | --- | --- | --- |
| DOC-01 | Conferir fontes da demo e adicionar caso com tabela | Contrato v0.1 | Texto esperado aponta a página/offset corretos |
| DOC-02 | Propor manifesto para exportação parcial | DOC-01 + Backend | Exemplo validado e lacunas registradas |
| BACK-01 | Revisar isolamento e acrescentar caso de autorização futura | Demo + política de acesso | Critério de acesso separado do filtro de processo |
| BACK-02 | Projetar pendência transacional/idempotente | Requisitos/autorização revisados | Mesmo pedido não duplica; conteúdo divergente conflita |
| HERM-01 | Confirmar Hermes oficial e versão | Coordenação | URL, commit, licença e extensão documentados |
| HERM-02 | Exercitar cliente comum e planejar integração | HERM-01 + API | Chamada rastreável; estágio real/smoke explícito |
| LANG-01 | Exercitar cliente e propor estado do grafo | API | Estado/encerramento revisados |
| LANG-02 | Fixar versão e testar limites de ciclo | Modelo/orçamento | Parada por limite sem sequência fixa |
| INFRA-01 | Rodar Compose e testar persistência/recovery | Docker | Reinício e restauração separados com evidência |
| INFRA-02 | Conferir proteções e orientar atualização manual das equipes | Coordenação + responsáveis | Checks/revisão mantidos; equipe demonstra fetch e merge preservando seus commits |
| MET-01 | Revisar tarefa piloto e criar mais duas | Documentos + domínio | Rubricas/evidências definidas antes da execução |
| MET-02 | Definir plano pareado e orçamento final | Coordenação + agentes | Unidade de análise/repetições e freeze documentados |
| COORD-01 | Confirmar pessoas e decisões pendentes | Guias | Campos nominais e ADRs preenchidos |

# Glossário rápido

| Termo | Significado |
| --- | --- |
| SEI | Sistema Eletrônico de Informações; usamos cópias exportadas manualmente. |
| Processo | Conjunto de documentos ligados a uma demanda administrativa. |
| Metadados | ID, processo, versão, origem, página e outras informações do documento. |
| API | Interface para solicitar operações ao backend. |
| Ferramenta / tool | Operação com entrada, saída e erros definidos, selecionada pelo agente. |
| Backend | Serviço que valida/executa operações e acessa o banco. |
| Chunk | Trecho recuperável com referência à origem. |
| Embedding | Representação numérica para comparar similaridade; não treina a LLM. |
| Recuperação | Busca de trechos relevantes com filtros e limites. |
| RAG | Recuperação de evidências para fundamentar geração de resposta. |
| Corpus | Conjunto versionado de documentos. |
| Completude | Cobertura conhecida da exportação: completa, parcial ou desconhecida. |
| OCR | Reconhecimento de texto em imagens, sujeito a erros. |
| LLM | Modelo de linguagem acessível por endpoint externo configurável. |
| Estado do agente | Mensagens e informações da execução que orientam o próximo passo. |
| Grafo | Nós e conexões representando transições possíveis na execução. |
| Harness | Código/configuração que executa e mede tarefas. |
| Idempotência | Repetir operação sem duplicar seus efeitos. |
| Container | Execução de serviço com dependências e isolamento definidos por imagem. |
| Volume | Armazenamento persistente mesmo após recriar container. |
| VPS | Servidor virtual contratado; não inclui uma LLM por definição. |
| Branch | Linha de trabalho no histórico Git. |
| Commit | Registro identificado de uma alteração. |
| PR | Pull request, proposta revisável de integrar uma branch em outra. |
| Merge | Integração de históricos; merge commit preserva os pais. |
| CI | Verificações automáticas de mudanças. |
| Implantação | Colocar versão aprovada em execução no servidor. |
| Rollback | Retomar versão anterior, considerando compatibilidade dos dados. |

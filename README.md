# Projeto Hermes: Estudo Comparativo de Agentes Autônomos em Documentos Administrativos e Institucionais

**Centro de Inovação em Inteligência Artificial (CIIA) - Universidade do Distrito Federal (UnDF)**

## 1. Apresentação

O presente repositório contém as especificações, documentação e artefatos de implementação do Projeto Hermes. O objetivo primordial do projeto é construir e avaliar comparativamente dois agentes autônomos capazes de consultar documentos administrativos exportados do Sistema Eletrônico de Informações (SEI) e executar tarefas específicas em um ambiente de testes rigorosamente controlado.

Um dos agentes utilizará o sistema executor "Hermes", enquanto o outro será implementado através do framework "LangGraph". Ambos compartilharão a mesma base documental, o mesmo catálogo de ferramentas e o mesmo modelo de linguagem (LLM). O intuito é garantir que a comparação das implementações se dê em condições idênticas e documentadas, propiciando a geração de evidências empíricas e a publicação de um artigo científico.

## 2. Arquitetura do Sistema

A arquitetura estabelecida separa logicamente a preparação documental, a execução das ferramentas e o controle cognitivo dos agentes, garantindo independência e testabilidade.

*   **Linguagem Base e API:** Python (versão 3.11 ou 3.12), orquestrando requisições através do FastAPI e esquemas Pydantic.
*   **Armazenamento de Dados:** PostgreSQL integrado via SQLAlchemy. O uso da extensão `pgvector` viabiliza a busca semântica em base vetorial.
*   **Extração e Ingestão Documental:** Emprego de PyMuPDF para extração de texto direto de PDFs e Tesseract (OCR em português) para reconhecimento de páginas digitalizadas.
*   **Orquestração e Execução:** Adaptadores Hermes e LangGraph atuando de maneira independente, mas consumindo a mesma API compartilhada (`HTTPX`).
*   **Infraestrutura e Ambiente:** Implantação em servidor Linux gerenciada via Docker Compose, com persistência adequada para garantir execuções reproduzíveis.

## 3. Estrutura das Equipes e Frentes de Trabalho

O desenvolvimento e a execução da pesquisa são distribuídos em frentes especializadas, coordenadas de maneira integrada:

*   **Documentos:** Responsável pelo inventário, extração (pipeline de ingestão), chunking, vetorização (embeddings) e conferência manual das fontes no escopo do SEI.
*   **Backend:** Encarregada do banco de dados, da API de comunicação e do catálogo central de ferramentas compartilhadas (por exemplo, `consultar_processo`, `buscar_documentos`, `registrar_pendencia`).
*   **Hermes:** Configuração do ambiente, integração de ferramentas e persistência de logs próprios do executor Hermes.
*   **LangGraph:** Construção do grafo de estado, definição de nós, arestas condicionais e limites do ciclo modelo-ferramenta utilizando a biblioteca LangGraph.
*   **Infraestrutura:** Gestão da VPS, containers, persistência de volumes, gerenciamento de rede e monitoramento.
*   **Metodologia:** Formulação das tarefas do benchmark, definição de rubricas de avaliação, métricas de sucesso e delineamento do desenho experimental.
*   **Coordenação:** Gerenciamento geral da arquitetura, priorização de tarefas, garantia das interfaces entre equipes e compilação do manuscrito científico.

## 4. Metodologia Experimental

O delineamento experimental tem como questão central: sob o mesmo modelo fundamental, ferramentas e base documental, como as implementações com Hermes e LangGraph diferem no que tange à conclusão de tarefas, latência, uso de ferramentas e custo financeiro?

As métricas primárias e secundárias capturadas durante os testes englobam:
1.  **Sucesso da Tarefa:** Verificação do atendimento a todos os requisitos e de ações confirmadas.
2.  **Uso de Ferramentas:** Coerência nas chamadas de funções e ausência de escritas indevidas (alucinações operacionais).
3.  **Qualidade Factual:** Nível de embasamento das afirmações baseadas estritamente nas fontes extraídas.
4.  **Latência e Consistência:** Tempo percorrido por etapa e constância dos resultados entre repetições iterativas.
5.  **Custo e Consumo:** Mensuração dos gastos associados ao consumo da infraestrutura e dos tokens dos modelos de linguagem.

O projeto estipula a realização de até 360 execuções isoladas ao longo das sessões de benchmark.

## 5. Requisitos Computacionais e Orçamento

Dada a natureza intensiva de processamento paralelo na extração de texto (OCR) e a exigência de memória RAM para a busca textual e vetorial no PostgreSQL, as especificações computacionais estipuladas contemplam:

*   **Hardware (VPS):** Instância virtualizada dotada de múltiplos núcleos de processamento (vCPU da linha AMD EPYC) e no mínimo 16 GB de memória RAM para suprimir riscos de sobrecarga (*Out of Memory*).
*   **Provedor e Integração de IA:** Hospedagem primária sob infraestrutura da Hostinger (Plano KVM 4) e processamento de linguagem viabilizado via agregador OpenRouter, permitindo a transição ágil de modelos durante o experimento.
*   **Estimativa Orçamentária:** Custo operacional tecnológico trimestral projetado entre R$ 694,00 e R$ 744,00.

## 6. Cronograma Consolidado

A execução é prevista para o trimestre final de 2026:
*   **Setembro:** Configuração de ambientes, estudo da stack tecnológica e extração inicial de dados piloto.
*   **Outubro:** Desenvolvimento final da base de dados, consolidação de APIs e encerramento do desenvolvimento de funcionalidades sistêmicas.
*   **Novembro:** Congelamento de versão de código (code freeze), deflagração das rodadas do experimento principal e início do fechamento dos resultados estatísticos.
*   **Dezembro (até 10/12):** Verificação de materiais, aprovação final e submissão do manuscrito científico resultante da pesquisa.

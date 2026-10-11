# Backlog de tarefas por área

## 1. Data & RAG (Equipe de Documentos) — André Vital

**Objetivo:** Transformar os processos exportados do SEI em uma base pesquisável, rastreável e auditável, garantindo que cada trecho recuperado preserve o documento e a página originais.

- **Task 1.1 — Catalogação e Inventário com Hash SHA-256:** Catalogar processos e arquivos com metadados de origem, data de coleta, escopo exportado e hash SHA-256 para auditar a integridade e descartar duplicidades.
- **Task 1.2 — Higienização de Dados e Conformidade LGPD:** Tratar e sanitizar dados sensíveis e pessoais do acervo de testes segundo o protocolo institucional e a metodologia do estudo antes da fase de chunking.
- **Task 1.3 — Extração de Texto e Pipeline de OCR (Tesseract):** Implementar a extração textual página a página via PyMuPDF e configurar OCR via Tesseract (em português) para páginas digitalizadas ou escaneadas, preservando o layout de tabelas.
- **Task 1.4 — Chunking Semântico com Injeção de Metadados:** Estruturar a divisão semântica em trechos de 300 a 600 tokens com overlap, vinculando obrigatoriamente `processo_id`, `doc_id`, `pagina` e `versao_base` em cada chunk.
- **Task 1.5 — Indexação Híbrida e Validação de Consultas:** Configurar busca por correspondência exata no PostgreSQL e busca vetorial via `pgvector`, realizando a validação de 10 consultas de referência com a equipe de Metodologia.

**Milestone:** Ingestão de 5 processos fictícios com validação comprovada das fontes para 10 consultas de referência.

---

## 2. Backend & Tools (Regras de Negócio e API) — Roger Quinelato

**Objetivo:** Implementar a lógica administrativa do SEI e expor 6 ferramentas REST comuns e padronizadas para ambos os executores.

- **Task 2.1 — Modelagem Relacional e Migrações (PostgreSQL + Alembic):** Estruturar a persistência em PostgreSQL com SQLAlchemy e implementar o controle de versões de esquema através do Alembic.
- **Task 2.2 — API REST e Validação de Esquemas (FastAPI + Pydantic):** Desenvolver as rotas FastAPI e os modelos Pydantic estritos (`BaseModel`, `Field`) para validação dos corpos de requisição e respostas JSON.
- **Task 2.3 — Catálogo de Ferramentas de Leitura:** Desenvolver e expor os endpoints e contratos para `consultar_processo`, `buscar_documentos`, `ler_documento` e `consultar_requisitos`.
- **Task 2.4 — Ferramentas de Escrita e Idempotência Rígida:** Desenvolver os endpoints para `registrar_pendencia` e `salvar_minuta`, implementando `chave_idempotencia` para prevenir duplicidade em reexecuções.
- **Task 2.5 — Gerenciamento de Execuções e Contexto Autenticado:** Implementar rotas `/runs` para criação e acompanhamento de tarefas, garantindo que os identificadores de execução venham do contexto autenticado do worker.

**Milestone:** Endpoints funcionais de consulta de processo e registro idempotente de pendências com testes de validação.

---

## 3. LangGraph (Orquestração Baseada em Grafos e Estados) — João Enomoto

**Objetivo:** Implementar o segundo pipeline autônomo modelando o ciclo decisório como um grafo de estados explícitos, nós determinísticos e arestas condicionais.

- **Task 3.1 — Construção do Grafo de Estados (StateGraph + MessagesState):** Modelar formalmente o nó de raciocínio (LLM), o nó executor de ferramentas (`ToolNode`) e as arestas condicionais de tomada de decisão (`add_conditional_edges`).
- **Task 3.2 — Conectividade Assíncrona com HTTPX:** Conectar as funções do agente às ferramentas da API compartilhada utilizando cliente assíncrono HTTPX com timeouts explícitos.
- **Task 3.3 — Checkpoints e Persistência de Estado:** Configurar pontos de salvamento e recuperação de estado (checkpoints) para suporte a resiliência em falhas transitórias.
- **Task 3.4 — Gestão de Limites Operacionais e Recursão:** Configurar limite rígido de recursão (`recursion_limit`) e travas de tempo/chamadas para evitar loops infinitos no grafo.
- **Task 3.5 — Tratamento Estruturado de Exceções:** Implementar tratamento específico para processos inexistentes, buscas sem resultado, exportações parciais e argumentos inválidos.

**Milestone:** Ciclo completo agente-ferramenta em grafo com chamada externa, transição condicional documentada e encerramento.

---

## 4. AI Infra (Infraestrutura, Hospedagem e Ambientes) — João Enomoto

**Objetivo:** Provisionar e gerenciar a infraestrutura estável, garantindo conteinerização, persistência e total separação entre aplicação e endpoint de inferência.

- **Task 4.1 — Servidor VPS Linux e Hardening de Segurança:** Preparar o servidor VPS (ex.: Hostinger), regras de firewall, acesso SSH protegido e proxy reverso HTTPS.
- **Task 4.2 — Conteinerização via Docker Compose:** Criar Dockerfiles e `docker-compose.yml` isolando API FastAPI, banco PostgreSQL (com extensão `pgvector`) e workers em containers.
- **Task 4.3 — Gestão de Volumes Persistentes e Armazenamento:** Configurar volumes nomeados para o banco de dados e diretórios de arquivos (originais, textos extraídos e minutas versionadas).
- **Task 4.4 — Configuração do Endpoint LLM e Segredos:** Estabelecer canal seguro e autenticado com o servidor com GPU ou API autorizada, gerenciando variáveis de ambiente sem expor segredos no Git.
- **Task 4.5 — Rotinas de Backup, Restauração e Limpeza:** Implementar rotinas automatizadas de backup do banco e scripts de reinicialização limpa dos volumes entre as rodadas do benchmark para evitar contaminação.

**Milestone:** Subir a stack Docker Compose (API + PostgreSQL) na VPS demonstrando persistência íntegra após reinício forçado.

---

## 5. Hermes (Integração do Executor Autônomo) — Gustavo Antônio

**Objetivo:** Integrar e configurar o motor Hermes no runtime do projeto, conectando seu ciclo operacional às ferramentas compartilhadas do Backend.

- **Task 5.1 — Fixação de Repositório e Mapeamento de Tool Calling:** Mapear o software-fonte, realizar auditoria de licenças, fixar tag/commit estável e mapear o mecanismo nativo de tool calling.
- **Task 5.2 — Loop Operacional e Conexão HTTP à API:** Conectar o ciclo do runtime ao endpoint LLM e despachar chamadas JSON padronizadas contra a API de ferramentas do Backend.
- **Task 5.3 — Isolamento de Sessões e Reset de Contexto:** Garantir execuções estanques vinculadas a um `run_id` global único, impedindo a contaminação ou persistência indevida de histórico entre tarefas.
- **Task 5.4 — Padronização de Prompts e Instruções de Evidência:** Configurar o prompt de sistema para instruir a consulta de requisitos, preservação de referências e declaração explícita de limites da base.
- **Task 5.5 — Coleta de Logs Estruturados para Auditoria:** Configurar a exportação detalhada de eventos contendo prompts, tokens consumidos, chamadas executadas e retornos das ferramentas no formato comum do projeto.

**Milestone:** Chamar uma ferramenta fictícia via API no loop do Hermes e exportar o log estruturado completo da sessão.

---

## 6. Evaluation / Metodologia (Rigor Científico e Testes) — Gustavo Antônio

**Objetivo:** Estabelecer o protocolo científico, construir o benchmark de casos de teste com gabarito homologado e conduzir a análise estatística comparativa.

- **Task 6.1 — Construção do Catálogo de Tarefas e Cenários:** Criar 12 a 15 tarefas piloto para desenvolvimento e selecionar/reservar de 40 a 60 tarefas para a bateria final de testes.
- **Task 6.2 — Definição de Gabaritos e Rubricas com Especialista:** Homologar checklists normativos e critérios factuais de avaliação com um especialista no domínio administrativo do SEI.
- **Task 6.3 — Pipeline de Apuração de Métricas (TUA, CTCE, F1, Latência):** Estruturar os scripts para cálculo automatizado de Taxa de Sucesso, Precisão no Uso de Ferramentas (TUA), Custo por Tarefa Concluída (CTCE), Latência e Consistência.
- **Task 6.4 — Protocolo de Avaliação Cega de Textos:** Definir a metodologia de duplo avaliador cego com amostra prévia para julgamento da qualidade factual e de redação das respostas e minutas.
- **Task 6.5 — Garantia de Pareamento Experimental e Análise Estatística:** Controlar a equivalência exata de condições (mesmo modelo, mesmas ferramentas, ordem alternada) e aplicar testes estatísticos apropriados para o manuscrito.

**Milestone:** Protocolo experimental homologado com as primeiras 5 tarefas de teste com gabaritos detalhados e rubricas validadas.

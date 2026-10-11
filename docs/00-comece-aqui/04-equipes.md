# Guias das equipes

Qual é a sua equipe? Escolha abaixo para ver o que ela faz, quem são as pessoas e qual é sua primeira tarefa.

Antes de programar, tire 30 minutos para concluir as etapas essenciais de onboarding:
1. **Leia** o [Glossário](03-glossario.md) para entender os termos técnicos do projeto.
2. **Rode a demo local** seguindo o [Início rápido](01-inicio-rapido.md).
3. **Configure o seu Git** seguindo o [Fluxo Git obrigatório](02-fluxo-git.md).
4. **Assuma sua tarefa** no [Backlog](../01-overview/backlog.md) definindo o responsável e o revisor da sua equipe.

---

## Equipes do Projeto

### [Data & RAG (Documentos)](../03-equipes/documentos.md)
**Missão:** Extrair textos de PDFs do SEI, fazer chunking inteligente e criar o motor de busca (RAG) em PostgreSQL.
- **Membros:** André Vital, Victor Hugo, Vinícius Melo, Lucas Farias.

### [Backend & Tools](../03-equipes/backend.md)
**Missão:** Desenvolver a API REST central em FastAPI que conecta o banco de dados às ferramentas dos agentes autônomos.
- **Membros:** Roger Quinelato, Letícia Pires.

### [LangGraph (Orquestração de Grafos)](../03-equipes/langgraph.md)
**Missão:** Programar pipelines de decisão e raciocínio de IA estruturados como grafos direcionados para automação de análise.
- **Membros:** João Enomoto, Igor Razzi.

### [Hermes (Agente Autônomo)](../03-equipes/hermes.md)
**Missão:** Configurar, tunar e acoplar o executor nativo autônomo (Hermes) consumindo as APIs REST do Backend.
- **Membros:** Gustavo Antônio.

### [AI Infra (Hospedagem)](../03-equipes/infra.md)
**Missão:** Conteinerizar (Docker), proteger e publicar a aplicação na nuvem (Hostinger e VPS), gerenciando deploy e segurança.
- **Membros:** Daniel Lucas, Danilo Moura.

### [Evaluation (Metodologia)](../03-equipes/metodologia.md)
**Missão:** Homologar gabaritos com especialistas e rodar testes para medir a precisão (F1, Taxa de sucesso) das respostas da IA.
- **Membros:** Gustavo Antônio, Nelson Neto, Hugo Coelho, Sarah Leticia, João Pedro, Isaac Joaqu.

---

## Coordenação do Projeto

A coordenação orienta as tarefas, destrava problemas técnicos e gerencia acessos. Procure a pessoa certa no nosso canal de comunicação (WhatsApp ou Discord) dependendo da sua necessidade:

- **Gustavo Antônio:** Arquitetura do Hermes, Metodologia, prazos gerais e dúvidas conceituais.
- **André Vital:** Acesso à base de documentos, regras do RAG, LGPD e dúvidas de extração de dados.
- **João Enomoto:** Dúvidas de DevOps, servidores (VPS/Docker), LangGraph e fluxo Git/GitHub avançado.
- **Roger Quinelato:** Estrutura da API, FastAPI, modelagem do PostgreSQL e contratos de endpoints.

> **Precisa de ajuda urgente com código ou Git?** Poste o erro completo no chat e marque o coordenador responsável pela sua área.

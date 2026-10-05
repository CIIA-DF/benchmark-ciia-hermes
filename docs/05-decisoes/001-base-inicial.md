# ADR 001 — base inicial

Data: 29/09/2026. Situação: escolha técnica inicial implementada localmente, sujeita à revisão da coordenação.

Contexto: havia README e dois PDFs, sem código; Git limpo em main, commit 48ee67223fde1935113aea244d706ae71c24bb5d, remote CIIA-DF/benchmark-ciia-hermes. Não havia AGENTS.md. Só main era conhecida localmente/remotamente no clone.

Escolhas: Python 3.12 com uv.lock; FastAPI/Pydantic e SQLAlchemy; PostgreSQL 17/Compose; SQLite para primeiro uso sem Docker. Dependências exatas e hashes no lock. Imagens têm tags de versão; congelar digests antes dos experimentos finais. Código fica nos componentes pedidos, sem camada src duplicada.

Demo: JSON sintético paginado, busca literal, chunks de 140 caracteres/20 de sobreposição. IDs/versões rastreáveis, corpus imutável e ingestão transacional. As três leituras estão implementadas; requisitos e escritas são contratos com resposta 501.

Git: branches permanentes determinadas pela coordenação e merge commits. A proposta de propagação automática registrada em 29/09 foi **substituída em 30/09/2026 pela [ADR 002](002-atualizacao-manual-equipes.md)**: a equipe passa a incorporar main manualmente. Essa revisão afeta apenas o fluxo Git; as escolhas da base técnica permanecem. Nenhum push remoto foi autorizado nesta preparação.

Alternativas adiadas: OCR/PDF, embeddings/pgvector, migrações, observabilidade completa e agentes reais. Hermes precisa de repositório/versão; LangGraph ainda não instalado. Endpoint de inferência é configurável e externo. SQLite não valida o comportamento operacional de PostgreSQL.

Responsáveis pela ratificação: André/Gustavo/João Enomoto e líderes técnicos a preencher. PDFs são preservados; suas estimativas não são requisitos medidos. Datas e volumes experimentais precisam ser confirmados antes do congelamento.

# Arquitetura e limites do MVP

Pipeline → banco → ferramentas HTTP → adaptadores → endpoint externo da LLM. A ingestão acontece antes das tarefas: não se reextrai/reindexa o corpus a cada pergunta. Infra mantém configuração, volumes e saúde; Metodologia especifica a avaliação.

## Fronteiras

Documentos prepara extração, qualidade, chunking, metadados, cobertura e evidências. Backend expõe a busca, aplica filtros e valida operações. Mudanças na recuperação exigem revisão conjunta. O agente seleciona ferramentas; somente o backend deverá executar escritas autorizadas. Adaptadores não recebem acesso direto ao banco.

Hoje o pipeline aceita JSON sintético paginado. Chunks usam 140 caracteres e sobreposição de 20, sem atravessar páginas. Offsets são índices de caracteres Python, início inclusivo e fim exclusivo no texto validado da página. Parâmetros são didáticos: precisam ser avaliados para PDFs, tabelas e tokens.

Chaves de processo/documento incluem corpus_version. IDs de chunks derivam de processo, documento, corpus, hash, página e offsets. Alterar conteúdo/chunking exige nova versão do corpus. Ingestão usa uma transação; repetição idêntica não duplica. Concorrência de ingestão pode falhar por constraint: confirmar o estado antes de tentar de novo. Só a rotina administrativa local de ingestão grava hoje.

Busca atual: substring literal, sem ranking, limite máximo 20, filtro de processo/corpus antes do limite, ordem determinística por documento/ID. Curingas % e _ são escapados. Maiúsculas Unicode podem ter comportamento diferente entre SQLite e PostgreSQL; avaliar normalização antes de medir recuperação. Resultado vazio não comprova ausência no processo original.

## Stack e evolução

Python 3.12, FastAPI/Pydantic, SQLAlchemy 2, PostgreSQL 17 no Compose. SQLite facilita o primeiro uso; CI tem job PostgreSQL. `create_all` cria o schema inicial, mas não migra tabelas. Antes de modificá-las, introduzir migrações revisadas, backup e rollback.

PDF/PyMuPDF, OCR/Tesseract, embeddings e pgvector são extensões previstas, não instaladas. Adotá-las exige corpus de validação e parâmetros registrados. Redis, Kubernetes e filas dedicadas não são necessários agora.

Os adaptadores compartilharão `AgentAdapter`, `ToolContext`, `ToolClient` e `ModelConfig`, com LLM_BASE_URL, LLM_MODEL, LLM_API_KEY e timeout. O ponto de integração não implementa inferência; verificar protocolo e tool calling do provedor. Não há GPU ou assinatura de LLM presumida na VPS.

## Acesso e observabilidade

API sem autenticação, somente para dados sintéticos em loopback/rede interna. Filtro de processo é isolamento funcional, não autorização por usuário. Autenticação, autorização por processo e proteção de rede são necessárias antes de uso compartilhado com corpus real. Escritas retornam 501.

Healthcheck consulta banco; erros não ecoam entradas ou SQL; access logs estão desativados. Não existe ainda coletor de métricas/traces nem armazenamento de ExperimentRun. Instrumentação futura registra IDs, duração, status e versões sem conteúdo/chaves. Veja [protocolo](../evaluation/protocol.md) e [operação](runbooks/operations.md).

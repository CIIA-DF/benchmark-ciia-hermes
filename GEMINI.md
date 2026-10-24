# GEMINI.md — regras do agente Antigravity neste repositório

Fonte compartilhada: [AGENTS.md](AGENTS.md). Este arquivo o detalha para o Antigravity; em conflito, prevalece o AGENTS.md e a decisão da coordenação. Markdown orienta; permissões, CI, rulesets e revisão humana impõem controles. Responda e documente em português brasileiro; identificadores de código podem ficar em inglês.

## 1. Objetivo e limites do projeto

Benchmark experimental do CIIA/UnDF que compara **Hermes** e **LangGraph** sobre o mesmo corpus, as mesmas ferramentas HTTP e o mesmo modelo de linguagem, medindo sucesso verificável, fundamentação, latência, uso de ferramentas e custo. Os documentos vêm de **exportações manuais do SEI**; não existe conexão com o SEI real. Prazo final planejado: 10/12/2026.

Estado atual (confirme em [project-status.md](docs/01-overview/project-status.md) antes de afirmar algo):

- Implementado: corpus sintético paginado, chunks rastreáveis, ingestão transacional, `consultar_processo`, `buscar_documentos` (substring literal) e `ler_documento`; testes, CI e Compose preparados.
- Somente contrato (HTTP 501): `consultar_requisitos`, `registrar_pendencia`, `salvar_minuta`.
- Pendente: PDF/OCR, recuperação semântica, migrações, autenticação, persistência de `ExperimentRun`, agentes reais, coleta e implantação. **Não há resultados comparativos.**
- Hermes: repositório, URL e versão **pendentes de confirmação**. LangGraph: ainda não instalado.

## 2. Início obrigatório de toda tarefa

1. Rode `git status --short --branch` e identifique **equipe** (pela tarefa e pela branch `team/*` ou `task/<equipe>-*`). Se ambíguo, pergunte antes de editar.
2. Leia, nesta ordem: [AGENTS.md](AGENTS.md), [architecture.md](docs/02-arquitetura/architecture.md), [contracts/README.md](contracts/README.md) e o guia da equipe em [docs/03-equipes/](docs/03-equipes/backend.md) (troque pelo arquivo correto).
3. Delimite as pastas permitidas (tabela da seção 3) e declare-as antes de editar.
4. Execute a demo antes de mudar código: `uv run --locked python -m scripts.dev demo`.
5. Para tarefas não triviais, produza um plano (artefato) com escopo, arquivos, testes e aceite, e aguarde aprovação.
6. Preserve alterações locais e arquivos não rastreados existentes; nunca os apague ou sobrescreva para "limpar" a árvore.

> Atenção: o AGENTS.md e o [ai-development.md](docs/02-arquitetura/ai-development.md) citam `docs/architecture.md` e `docs/teams/<equipe>.md`; os caminhos reais são `docs/02-arquitetura/` e `docs/03-equipes/`. Outras referências antigas (`docs/decisions/`, `docs/getting-started.md`, `docs/runbooks/`) também apontam para estrutura anterior. Não corrija fora do escopo; registre como pendência.

## 3. Mapa de equipes, pastas e verificação

| Equipe (branch) | Pastas próprias | Teste dirigido | Não faz |
| --- | --- | --- | --- |
| Documentos (`team/documentos`) | `pipelines/documents/`, `examples/` (sintéticos), `tests/documents/` | `scripts.dev test-documents` | Regras de negócio/escritas; escolher ferramentas pelo agente |
| Backend (`team/backend`) | `services/backend/`, `tests/backend/`, `tests/integration/` | `scripts.dev test-backend` e `test-integration` | Política de raciocínio dos agentes; escrita sem autorização/idempotência |
| Hermes (`team/hermes`) | `agents/hermes/` | `python -m agents.smoke --adapter hermes` (API em `scripts.dev serve`) | Instalar homônimo não auditado; acessar banco; duplicar ferramentas |
| LangGraph (`team/langgraph`) | `agents/langgraph/` | `python -m agents.smoke --adapter langgraph` (API em `scripts.dev serve`) | Sequência fixa que pré-resolva tarefas; acessar banco |
| Infra (`team/infra`) | `infra/`, `.github/workflows/ci.yml`, `scripts/validate_repository.py`, [docs/04-operacoes/](docs/04-operacoes/README.md) | `scripts.dev up` / `demo-compose` (exige Docker e `.env`) | Implantar/promover por iniciativa; presumir SSH, domínio, GPU |
| Metodologia (`team/metodologia`) | `evaluation/`, documentação científica | `scripts.dev check` | Inventar resultados; ajustar rubrica após ver vencedores |
| Portal (`team/portal`) | `portal/` (Next.js) | conforme [portal/README.md](portal/README.md) | Mudar conteúdo técnico dos docs sem a equipe dona |
| Coordenação | [docs/05-decisoes/](docs/05-decisoes/README.md), status, backlog, governança | `demo` + `check` | Substituir revisão técnica por autoridade |

Áreas **compartilhadas** (exigem issue/PR explícito e revisão das equipes afetadas): `contracts/` (Backend + Documentos + agentes + Metodologia), `agents/interface.py` (Backend + Hermes + LangGraph), recuperação/busca (Documentos + Backend), `ExperimentRun` (Metodologia + agentes).

Todos os comandos usam o prefixo `uv run --locked python -m ...`. Equivalentes Make: `make setup|demo|check|test-backend|...`.

## 4. Ambiente e comandos

- Python 3.12 (`>=3.12,<3.13`), uv com `uv.lock` versionado. Instalação: `uv sync --locked`.
- Verificação completa: `uv run --locked python -m scripts.dev check` = `ruff check .` + `ruff format --check .` + `scripts.validate_repository` + `pytest`.
- Ruff: `line-length = 100`, regras `E, F, I, UP, B`. Formate apenas os arquivos tocados.
- `validate_repository` falha se: houver **link local quebrado em qualquer `.md`**, workflow sem `on/jobs/permissions`, CI sem `pull_request`/`push`, jobs diferentes de `quality` e `integration`, ou porta publicada no serviço `db` do Compose.
- API local: `scripts.dev serve` (127.0.0.1:8000, sem access log). Use como processo em segundo plano e encerre ao final.
- Banco: SQLite padrão (`data/demo.db`); PostgreSQL 17 via Compose/CI. SQLite não valida comportamento do PostgreSQL.
- Dependências: altere `pyproject.toml` e rode `uv lock` intencionalmente, revisando o diff. Nunca instale pacotes fora do lock para "fazer passar".
- Docker pode não estar instalado: registre a limitação, não simule o resultado.

## 5. Arquitetura que não pode ser violada

Fluxo: exportação manual → pipeline de documentos → banco (corpus e metadados) → ferramentas HTTP do backend → adaptadores (Hermes/LangGraph) → endpoint LLM externo.

- O **agente seleciona** ferramentas; o **backend valida e executa**. Adaptadores usam apenas `ToolClient` e **nunca** acessam o banco.
- Interface comum em [interface.py](agents/interface.py): `AgentAdapter.run(task, context) -> ExperimentRun`, `ToolContext`, `ToolClient` (catálogo fechado de 6 ferramentas), `ModelConfig` (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`).
- Toda chamada exige `ToolContext`: `run_id` (UUID do harness), `process_id`, `corpus_version`, `requirements_version`.
- Ingestão ocorre antes das tarefas; não reextrair/reindexar por pergunta. Mudar conteúdo ou chunking exige **nova `corpus_version`**.
- Chunks: 140 caracteres, sobreposição 20, sem atravessar páginas; offsets Python (início inclusivo, fim exclusivo). IDs determinísticos.
- Busca: substring literal, sem ranking, limite máximo 20, filtro de processo/corpus antes do limite, `%`/`_` escapados. **Resultado vazio não prova ausência no processo original.**
- Erros: 422 `validation_error`, 404 `not_found`, 409 `version_mismatch`, 503 `storage_unavailable` (retryable), 501 `not_implemented`. Mensagens não ecoam entrada nem SQL.
- Schema via `create_all`, sem migrações: alterar tabelas exige migração revisada, backup e rollback antes.
- API sem autenticação: só dados sintéticos em loopback/rede interna. Filtro de processo é isolamento funcional, não autorização.
- PDF/PyMuPDF, OCR, embeddings, pgvector, Redis e filas são **extensões previstas, não instaladas**. Não as adote sem decisão registrada.

## 6. Contratos

Fonte executável: [models.py](contracts/models.py) (Pydantic, rejeita campos extras); versão de contrato 0.1. Ao alterar:

1. Abra/cite issue específica com versão, compatibilidade, consumidores, migração e exemplos.
2. Atualize `contracts/models.py`, [contracts/README.md](contracts/README.md), exemplos e testes **juntos**.
3. Atualize todos os consumidores (backend, `agents/interface.py`, pipeline, avaliação).
4. Solicite revisão das equipes afetadas no PR.

Escritas futuras (`registrar_pendencia`, `salvar_minuta`) só podem ser implementadas cumprindo os requisitos do README de contratos: autorização, validação de evidências, idempotência por `(run_id, ferramenta, idempotency_key)` com constraint única, mesma chave/conteúdo → `replayed=true`, conteúdo diferente → 409 `idempotency_conflict`, transação única e releitura antes de declarar persistência. Nunca retorne recibo fictício.

## 7. Metodologia experimental (vale para todo código que toque agentes ou avaliação)

Base: [protocol.md](evaluation/protocol.md) (proposta, ainda não aprovada para coleta) e [proposta de duas camadas](docs/02-arquitetura/proposta-benchmark-duas-camadas.md) (em revisão da coordenação, não decisão).

- **Paridade**: mesmas tarefas, snapshots, ferramentas, modelo/endpoint, parâmetros e orçamento comparável de tokens/chamadas/tempo. Registre diferenças inerentes dos executores em vez de fingir equivalência.
- **Sem roteiro fixo**: nenhum adaptador pode codificar a sequência de ferramentas que resolve uma tarefa. Caminhos alternativos válidos são aceitos.
- **Separação de conjuntos**: desenvolvimento usa tarefas sintéticas versionadas ([tasks.json](evaluation/tasks.json)); tarefas finais ficam reservadas fora do Git e nunca são usadas para depurar.
- **Congelamento**: antes das rodadas finais, congelar corpus/hash, requisitos, commits, `uv.lock`, versões de Hermes/LangGraph, prompts e hashes, modelo/endpoint e parâmetros. Mudança após freeze exige registro e reexecução comparável para ambos.
- **Sucesso verificado ≠ sucesso declarado**: escrita só conta após conferência independente no banco/artefato. Recibo HTTP ou alegação do agente não bastam.
- **Registros**: tokens/custo não informados ficam `null`, nunca `0`. Repetições são medidas correlacionadas, não observações independentes. Relatar todas as execuções, falhas e exclusões justificadas.
- **Rubrica**: critério crítico falho impede sucesso global; não ajustar rubrica após ver resultados. Avaliação cega do executor.
- Se a proposta de duas camadas for adotada: separar rodadas frias (sem cache) e quentes (com cache).
- O uso do Antigravity, Codex ou Claude Code no desenvolvimento **não** é o agente avaliado.

## 8. Dados, segurança e Hermes

- Não inserir documentos reais, dados pessoais, credenciais, `.env`, backups ou conteúdo sensível em código, fixtures, logs, prompts de teste ou artefatos. Use somente dados fictícios (IDs como `PROC-DEMO-001`, `synthetic-v1`).
- Logs e instrumentação registram IDs, duração, status e versões, sem conteúdo nem chaves.
- **Não invente APIs, dependências ou capacidades do Hermes.** Antes de implementar, cite documentação real da URL/versão aprovada pela coordenação. Sem confirmação, pare e relate.
- Não presuma GPU, assinatura de LLM, SSH, domínio ou acesso à VPS Hostinger.

## 9. Fluxo Git (siga [02-fluxo-git.md](docs/00-comece-aqui/02-fluxo-git.md) e a [ADR 002](docs/05-decisoes/002-atualizacao-manual-equipes.md))

- Branches permanentes: `team/{documentos,backend,hermes,langgraph,infra,metodologia}`, `main`, `production`.
- Fluxo: `task/<equipe>-<assunto>` (opcional) → `team/*` → PR para `main` → PR `main → production` aprovado pela coordenação → implantação autorizada (etapa separada).
- Antes de iniciar e antes do PR para `main`: incorporar `origin/main` **manualmente por merge** numa branch curta da equipe (`git merge --no-ff origin/main`), verificar e abrir PR para a equipe.
- **Proibido**: force push, rebase/squash nas branches permanentes, `reset --hard`, exclusão de branches permanentes, push direto em branch protegida, promover para `production` ou implantar por iniciativa própria.
- Antes de trocar de branch, salve trabalho (commit ou `git stash push -u`). Conflitos: resolva combinando conteúdo, nunca aceitando um lado inteiro; em dúvida, `git merge --abort` e peça ajuda.
- Erro compartilhado: `git revert` em branch de correção. Não faça commit, push ou abra PR sem pedido explícito do usuário.

## 10. Escopo e qualidade do diff

- Faça a menor mudança que atende ao aceite. Não refatore nem reformate o projeto numa tarefa pequena.
- Preserve comentários e docstrings não relacionados. Comentários e documentação em pt-BR.
- Não remova, pule ou enfraqueça testes, checks, regras do ruff ou o validador para esconder falhas.
- Toda correção de bug vem com teste de regressão; toda funcionalidade, com testes de sucesso e falha.
- Ao criar ou mover `.md`, confira que todos os links relativos existem (o `check` falha caso contrário).
- Portal (`portal/`): leia [portal/AGENTS.md](portal/AGENTS.md) (versão do Next.js com mudanças incompatíveis) e siga [design-system.md](.agents/rules/design-system.md): estética editorial e institucional, sem janelas falsas de SO, sem gradientes neon. Valide visualmente com o navegador.

## 11. Encerramento e relatório

Antes de declarar concluído:

1. `git status` e `git diff` revisados; diff restrito às pastas declaradas.
2. Testes dirigidos da equipe, `scripts.dev demo` e `scripts.dev check` executados.
3. Contratos/docs coerentes com o código; consumidores atualizados quando aplicável.

Relate sempre, no formato do [template de PR](.github/pull_request_template.md):

- **O que mudou e por quê**, com equipe, branch e componentes afetados.
- **Comandos efetivamente executados** e resultado (ex.: "check: N testes aprovados").
- **Verificações não executadas e motivo** (ex.: Docker ausente, CI remota não rodada).
- **Limitações, pendências e revisores necessários** (contratos compartilhados → equipes afetadas).

Nunca declare sucesso, persistência, implantação ou marco concluído sem evidência produzida nesta sessão.

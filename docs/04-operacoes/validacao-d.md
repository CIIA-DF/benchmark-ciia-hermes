# Validação do bloco D — documentação das APIs

Data: 31/10/2026. Worktree oficial `backend-tools`, branch `team/backend`.
Escopo: consolidação documental após F/A/I. Sem alteração funcional da API, migração operacional, commit, push ou deploy.

## Causa e entrega

A referência anterior ainda descrevia erros pré-A0, omitia quotas e tratava etapas legadas como tentativas. Documentos incrementais também misturavam versões do projeto, API, registro experimental e exportação.

Foram entregues:

- [Referência vigente](../02-arquitetura/backend-api-atual.md): 21 fichas, incluindo as seis tools individualmente; autenticação, parâmetros, entrada, saída, status, regras comuns, limites e exemplos.
- [Exemplos versionados](../02-arquitetura/backend-api-exemplos.json) e [verificador](../../scripts/validate_api_docs.py): cobertura de operações, modelos de entrada, respostas, parâmetros e correspondência dos exemplos com o Markdown.
- [Índice atual](backend-estado-atual.md): implementação, evidência e liberação separadas; migrações 0001–0009 na data de D (a 0010 veio com o port J de 21/11/2026; ver o índice); itens propostos E/O/H identificados.
- [ADR 010](../05-decisoes/010-documentacao-interfaces.md): decisão documental, versões e compatibilidade, sem inventar aprovação ou release.
- Links de entrada nos READMEs, referência anterior e plano; conteúdo histórico preservado.

## Fluxo transacional documentado

Autorização técnica precede reserva lógica; reserva confirma antes do domínio. Efeito e fase correspondente são transacionais; tentativa recusada é registrada após rollback. Resposta preparada não prova entrega. Retry conserva ID, corpo e chave; não duplica efeito. Documentação distingue ledger legado, tentativa física, efeito, relato do agente e avaliação independente.

D não mudou essas transações. A correção local A7 foi identificada no código e nos registros existentes, sem declarar nova homologação comportamental por mera documentação.

## Verificações desta rodada

| Comando | Resultado nesta rodada |
| --- | --- |
| `uv run --locked python -m scripts.validate_api_docs` | 21 operações cobertas; exemplos de entrada válidos nos modelos e iguais aos publicados nas fichas |
| `uv run --locked python -m scripts.export_openapi --check` | Cópia versionada coerente; sem regeneração por D |
| `uv run --locked python -m scripts.validate_repository` | Links, YAML e invariantes aprovados |
| `uv run --locked python -m pytest tests/backend/test_openapi.py tests/integration/test_i1.py` | 32 aprovados em 135,86 s; consumidores síncrono/assíncrono e OpenAPI |
| `uv run --locked python -m pytest tests/backend/test_contract_security.py tests/backend/test_experiment_contract.py` | 20 aprovados em 73,31 s; segurança e registro experimental |
| `uv run --locked python -m ruff check scripts/validate_api_docs.py` | Aprovado |
| `uv run --locked python -m ruff format --check scripts/validate_api_docs.py` | Aprovado |
| `git diff --check` | Sem erros de whitespace; avisos locais de conversão CRLF/LF |

Total das duas seleções disjuntas: **52 testes aprovados**, sem skips. Aviso existente Starlette/HTTPX permanece. O verificador documental é adicional, não contado como teste pytest. A primeira checagem de lint encontrou uma linha longa no novo verificador; ela foi formatada e lint/formatação passaram novamente.

Não houve repetição da suíte completa: D não mudou comportamento de produção e foram executadas as regressões pertinentes a contratos e consumidores. A suíte integral histórica de I não é apresentada como nova execução de D. Os testes usam SQLite sintético; não acessam base operacional.

## Consumidores e limites

Revisão documental afeta quem consome API, catálogo e resultados: Backend, Documentos/RAG, Hermes, LangGraph, Metodologia e Infra. Interfaces/DTOs não foram alterados neste bloco; nenhum catálogo foi regenerado com conteúdo novo por D.

Exemplos usam dados sintéticos: validação estrutural não comprova recurso existente, autorização, qualidade semântica ou inferência. Exemplos bem-sucedidos de escritas exigem evidências obtidas do corpus carregado no ambiente experimental, nunca IDs inventados.

PostgreSQL, espera por travas, recuperação de backup, Nginx/Compose e agentes reais permanecem não homologados, conforme registros F/A/I. Nenhum ganho de latência, custo ou qualidade foi medido. Exportação canônica e indicadores permanecem E/O.

Implementação documental: entregue. Verificação documental e regressões dirigidas: aprovadas localmente. Liberação conjunta: pendente de revisão manual. Alterações locais preexistentes foram preservadas; esta entrega não lhes concede aceite automático.

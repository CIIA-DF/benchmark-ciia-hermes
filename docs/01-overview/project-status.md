# Estado do projeto e evidências

Data da preparação: 29/09/2026. Fluxo Git revisado em 30/09/2026. Prazo final planejado: **10/12/2026**.

## Antes desta preparação

Repositório em main, commit 48ee67223fde1935113aea244d706ae71c24bb5d, sem alterações locais. Remoto informado pelo Git: https://github.com/CIIA-DF/benchmark-ciia-hermes. Existiam README e dois PDFs, sem aplicação, automações ou AGENTS.md. PDFs e histórico preservados. Nenhuma configuração remota foi alterada e nenhuma branch foi publicada.

## Entregue localmente

Base Python 3.12 com dependências exatas/hashes em uv.lock; contratos Pydantic v0.1; JSON fictício, chunking rastreável e ingestão transacional; consulta de processo, busca textual limitada e leitura de documento. Scripts, Compose com PostgreSQL, instruções de contribuição/IA, guias de equipes, backlog e protocolo inicial.

CI de validação preservada. Conforme a [ADR 002](../05-decisoes/002-atualizacao-manual-equipes.md), a equipe incorpora main manualmente antes de iniciar tarefas e antes de integrar suas entregas. Uma atualização da main não abre PRs nem modifica branches de equipe automaticamente. O mecanismo anterior e seus testes exclusivos foram removidos; backend, contratos, pipeline, infraestrutura, metodologia e demais verificações permanecem.

## Revisão do fluxo em 30/09/2026

Removidos o workflow de propagação, o script que gerava PRs/auto-merge, seus oito testes exclusivos e o runbook de ativação. Os quatro arquivos removidos, ainda não versionados, receberam cópia de segurança temporária fora do repositório. O validador foi ajustado apenas para não depender do workflow retirado. Guias, backlog e instruções refletem a atualização manual.

Verificações desta revisão: `scripts.dev check` aprovou lint, formato, links/YAML e **16 testes da aplicação**; `scripts.dev demo` confirmou consulta e ingestão repetida sem novos chunks; `actionlint 1.7.12` validou a CI mantida; `git diff --check` não apontou erros. A busca por referências remanescentes deixou apenas registros históricos, instruções de desativação e a indicação explícita do fluxo manual.

A comparação de hashes antes/depois confirmou preservação do código da aplicação, contratos, pipeline, exemplos, infraestrutura, metodologia, CI, templates e dependências. A única alteração no código Python foi retirar a validação específica do workflow removido. Nenhum commit, push, configuração remota ou acesso à VPS foi realizado nesta revisão.

Consulta remota somente leitura: Git anunciou apenas main no commit original e nenhuma referência de PR. A API pública retornou 404; configurações administrativas não puderam ser auditadas. Veja a [conferência de pendências no GitHub](../04-operacoes/github-governance.md).

## Validação da preparação de 29/09/2026 (histórico)

Resultados da preparação original, anteriores à mudança do fluxo Git; a contagem de 24 inclui oito testes exclusivos do mecanismo agora removido:

| Verificação | Evidência |
| --- | --- |
| uv sync --locked | Ambiente instalado com Python 3.12.13 e uv 0.11.13 |
| scripts.dev check | Lint/formato, links locais/YAML e **24 testes aprovados** |
| scripts.dev demo | SQLite: quatro chunks persistidos; repetição inseriu zero; busca retornou origem |
| scripts.demo --url + servidor Uvicorn | Consulta/busca por HTTP em 127.0.0.1:8000 aprovadas; servidor encerrado após teste |
| agents.smoke --adapter hermes/langgraph | Ambos os testes HTTP aprovados; não são execuções dos agentes reais |
| actionlint 1.7.12 | Sintaxe/expressões dos dois workflows aprovadas; shellcheck/pyflakes externos desativados |
| check-jsonschema + schema oficial Compose | compose.yml válido no schema; não equivale a subir containers |
| Revisão Git/dados | git diff --check sem erros; dois PDFs com hashes idênticos ao HEAD; 81 arquivos de texto inspecionados sem padrões de chaves/tokens |
| scripts.dev up sem Docker | Falhou com mensagem orientando instalar Docker ou usar demo local |

Na preparação original, os testes cobriam contratos, tarefa sintética, offsets/fontes, filtros, leitura cruzada, ingestão repetida, rollback transacional, reconexão e o mecanismo Git agora retirado. Não foram criados commits, PRs remotos, infraestrutura ou resultados experimentais.

Aviso conhecido: a combinação resolvida de Starlette e HTTPX emite depreciação no cliente de testes; não houve falha nas verificações. Não foi ocultado por filtro de warnings. Revisar compatibilidade em atualização de dependências antes de congelar a versão experimental.

Docker/Compose não está instalado nesta máquina. PostgreSQL, build dos containers, backup/restauração e execução dos jobs no GitHub ainda não foram comprovados nesta sessão. VPS não foi acessada; não há evidência de implantação. CI contém job PostgreSQL dedicado, ainda a executar remotamente.

## Funcionalidades pendentes

PDF/OCR, recuperação semântica, requisitos institucionais validados, autenticação/autorização para uso compartilhado, escritas idempotentes, migrações de schema, instrumentação completa e persistência de ExperimentRun. Hermes/LangGraph reais e inferência externa ainda não integrados. Não foram produzidos resultados comparativos.

## Ativações e decisões

- GitHub: publicar branches ausentes após aprovação, preencher CODEOWNERS e configurar rulesets/checks/revisores. Conferir eventuais configurações antigas conforme a [governança](../04-operacoes/github-governance.md); não é necessária credencial de bot para a atualização manual das equipes.
- Hostinger: confirmar IP/SO/recursos/SSH, operadores, rede, segredo de banco, backup externo e janela autorizada; seguir runbook.
- Coordenação: responsáveis/contas e composição das vagas; Hermes exato; versão LangGraph; procedimento, especialista/corpus e acesso a dados; modelo/endpoint/orçamento; desenho final, volume de rodadas e veículo do artigo.

## Marcos planejados, sem declaração de conclusão

| Período | Entrega proposta | Situação |
| --- | --- | --- |
| Setembro/outubro | Base, integração, corpus piloto e formação | Esta preparação local é evidência parcial; confirmar demais entregas |
| Até 30/10 | Funcionalidades do piloto e protocolo | Planejado, sujeito à revisão |
| Até 06/11 | Congelamento de versões e avaliação final reservada | Planejado |
| Novembro | Coleta, conferência e análise | Não iniciada nesta base |
| Até 27/11 | Rascunho completo do artigo | Proposto nos PDFs; confirmar |
| Até 10/12 | Revisão final, reprodução e entrega | Prazo final planejado |

Veja [backlog](backlog.md), [decisão inicial](../05-decisoes/001-base-inicial.md), [decisão vigente do fluxo Git](../05-decisoes/002-atualizacao-manual-equipes.md) e [decisão de inferência e duas camadas](../05-decisoes/003-provedor-inferencia-openrouter.md).

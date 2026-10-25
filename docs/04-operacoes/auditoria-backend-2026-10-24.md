# Auditoria crítica de Backend & Tools — 24/10/2026

**Parecer: requisitos parcialmente atendidos. A entrega ainda precisa de correções
antes de ser aceita como backend completo do piloto.** As seis tools existem;
os defeitos abaixo não são ausência de endpoints, mas violações de consistência,
resiliência e rastreabilidade nas operações já implementadas.

## Escopo e fontes

Worktree: `C:\Users\roger\.codex\worktrees\backend-tools\benchmark-ciia-hermes`.
Branch: `team/backend` (interpretando `tem/backend` do pedido).
HEAD consultado: `d1498296ea8edd51add7f3cba4a456923f0bf408`.
Base incorporada: `origin/main` em `4987721e761cb35f6ebee00bff98d0bee15706b9`.

A auditoria considera arquivos modificados e não rastreados da worktree, pois
a implementação ainda não está commitada. O diff de commits contra a main
incorporada, isoladamente, não representa essa entrega local. Nenhum push, PR,
commit ou alteração da implementação foi realizado nesta auditoria.

Leitura prévia: os 64 Markdown existentes no projeto, incluindo regras,
onboarding, backlog, arquitetura, guias de todas as equipes, contratos,
operações, PRD/TDD, ADRs, protocolo, READMEs dos componentes e templates.
Também foram relidos os três PDFs do repositório: guia de 23 páginas, orçamento
de 7 páginas e objetivo dos agentes de 2 páginas. Depois foram inspecionados
código, migrações, configuração e testes. Houve revisão independente de um
agente com papel de CTO, com reproduções complementares.

Precedência: decisões atuais e PRD/TDD/contratos v0.2 definem o aceite desta
entrega; propostas históricas e a proposta de duas camadas não tornam cache,
painel comparativo ou implantação requisitos desta etapa. Corpus/recuperação
e agentes reais continuam com suas equipes. Essa divisão não elimina defeitos
no worker e na API compartilhados fornecidos pelo Backend.

## Defeitos confirmados

### A01 — Alta: reconexão pode perder texto na prévia SQLite

Evidência: `services/backend/execution.py`, `public_run` (linhas 527–560) e
`get_run` (584–587). Texto parcial e cursor são lidos em SELECTs separados.
`get_run` usa `engine.connect()`; o `FOR UPDATE` não fornece a trava esperada
no SQLite. A configuração atual permite que outro commit ocorra entre leituras.

Reprodução controlada com banco temporário e uma publicação concorrente:
ler texto vazio → confirmar delta `LOST`, sequência 3 → ler cursor 3.
A API devolveu `partial_answer=""`, `last_event_id=3`, enquanto o banco já
continha `LOST`. Retomar com `after=3` pula exatamente o trecho ausente.
Um único worker basta, pois ele concorre com a requisição do navegador.

Requisito afetado: **B08**, snapshot consistente para reconexão.
Falta garantir uma leitura atômica de texto/cursor no SQLite e acrescentar
regressão com interleaving de publicação e consulta. Não extrapolar esse
defeito específico para PostgreSQL: nele a trava de linha tem efeito.

### A02 — Alta: conversa pode mostrar execução concluída sem resposta

Evidência: `services/backend/execution.py:144`, `get_conversation` lê mensagens
antes de consultar runs; `portal/app/chat/page.tsx:470` renderiza a resposta de
sucesso pelas mensagens e só abre SSE se encontrar execução ativa.

Reproduzido **em SQLite e PostgreSQL 17**: finalizar o run entre a consulta de
mensagens e a de runs faz o mesmo GET devolver `messages=[user]` com
`run.status=succeeded`. Uma segunda consulta devolve `[user, assistant]`.
A interface pode ficar sem resposta e sem streaming até nova consulta.

Requisitos afetados: **B07/B08**, recuperação de histórico e resposta consistente.
Falta snapshot consistente do agregado conversa/mensagens/runs e regressão de
finalização concorrente. A UI também precisa reconciliar resultado terminal
quando a mensagem correspondente ainda não estiver no snapshot recebido.

### A03 — Alta para avaliação: histórico de tools não reconstrói as chamadas

Evidência: `services/backend/tools.py:31` emite evento somente após leitura
bem-sucedida; `services/backend/execution.py:650` devolve replay antes de
registrar evento; `:677` registra escrita sem duração. A exportação em
`scripts/export_chat.py:29` usa esses eventos, não um histórico completo de tentativas.

Reprodução: `ler_documento` inexistente → 404; `salvar_minuta` → 200;
repetir a mesma escrita → 200/replayed. O banco registrou somente **um** evento
de tool, de sucesso, sem duração nem `tool_call_id`. O erro e a repetição somem.
Entradas rejeitadas antes do handler também não possuem registro de tentativa.

Requisitos afetados: rastreabilidade do Guia pp. 14/18 e
[protocolo de avaliação](../../evaluation/protocol.md), com impacto na exportação B09.
Não é possível medir corretamente falhas, tentativas ou chamadas redundantes
usando esse histórico. Falta distinguir chamada/tentativa de efeito persistido,
com IDs correlacionáveis, duração, resultado e replay. A auditoria de falhas
precisa sobreviver ao rollback dos efeitos, sem registrar conteúdo sensível.

### A04 — Média: HTTP 503 no claim encerra o worker local

Evidência: `agents/worker.py:78` trata `TransportError`, mas `:86` executa
`raise_for_status()` fora desse tratamento. Um 503 com `retryable=true` faz
`work(..., once=False)` encerrar com `HTTPStatusError` após uma requisição.
Reproduzido com `httpx.MockTransport`, sem banco ou endpoint externo.

Na prévia sem Docker, uma indisponibilidade transitória deixa a fila sem
consumidor até intervenção. O reinício do container pelo Compose é apenas
uma mitigação nesse outro modo de execução.

Requisito afetado: recuperação controlada de falha temporária, Guia p. 14 e
protocolo de integração. Falta política explícita para erros recuperáveis,
com espera/tentativas limitadas e distinção de falhas definitivas de autorização.
Preservar a regra de não repetir cegamente uma reserva cuja confirmação se perdeu.

### A05 — Média: referências inventadas entram no relatório experimental

Evidência: `services/backend/execution.py:497` valida somente
`persisted_artifact_ids`; `contracts/models.py:178` admite nome arbitrário de tool
e referência de artefato sem validação de pertencimento em `tool_calls`.

Reprodução: concluir benchmark com `persisted_artifact_ids=[]`, mas uma chamada
de tool `ferramenta_inexistente` e `artifact_id` UUID inexistente dentro de
`tool_calls` retornou **HTTP 200**. Sem ExperimentRun, o mesmo sucesso foi
corretamente rejeitado com 422: o envelope é obrigatório, sua coerência é parcial.

Requisito afetado: contrato de conclusão do benchmark, que exige existência dos
artefatos declarados, e rastreabilidade do protocolo. Falta validar referências
de todos os campos e distinguir dados declarados pelo adaptador dos confirmados
pelo backend. Essa verificação estrutural não substitui avaliação semântica.

### A06 — Média: impedimento sem streaming é ocultado no chat

Evidência: `portal/app/chat/page.tsx:500` mostra apenas `run.partial_answer`
para falhas, com fallback genérico. Ignora `run.result.answer`, fontes e código
do resultado nesse bloco.

Reprodução HTTP: resultado `status=failed`, `answer="Impedimento fictício: falta
documento"`, `error_code=adapter_error`, sem deltas, foi aceito e persistido.
O snapshot contém essa resposta, `partial_answer=""` e somente a mensagem do
usuário. A lógica da interface exibe o aviso genérico em vez do impedimento.

Requisito afetado: jornada de retorno do agente e tratamento de impedimentos do
Guia p. 14. Falta apresentar resultado terminal, explicação e fontes disponíveis
também em falhas, mantendo essas mensagens fora da memória futura conforme o contrato.

### A07 — Média: OpenAPI descreve outro formato de erro

Evidência: `services/backend/app.py:79` retorna `ToolError` no handler de 422,
mas as rotas não declaram esse modelo nas respostas de erro. O OpenAPI de
`POST /tools/buscar_documentos` anuncia `HTTPValidationError` para 422.

Reprodução: requisição inválida retornou chaves `code`, `message`, `run_id`,
`retryable`; o schema publicado aponta a estrutura padrão `detail`.
Erros de negócio 401/403/404/409/503 também não estão descritos por modelo nas rotas.

Requisito afetado: **Task 2.2/B01**, contratos estáveis de entrada, saída e erros.
Falta declarar os modelos efetivos e testar correspondência entre OpenAPI e HTTP,
para que clientes gerados e equipes consumidoras recebam o contrato correto.

### A08 — Baixa: instruções atuais ainda contradizem a implementação

Evidência: `GEMINI.md:12` afirma três tools em 501, `:60` apresenta
`AgentAdapter.run`, `:66` diz que não há migrações e `:67` diz que não há autenticação.
O README mantém tabela e aviso antigos sob uma ressalva histórica genérica.
Guias dos agentes ainda orientam smoke com API iniciada sem a configuração
autenticada que o comando passou a exigir.

Requisito afetado: entrega reproduzível e documentação coerente. Falta atualizar
as instruções operacionais vigentes e identificar cada seção histórica de forma
inequívoca, preservando os ADRs históricos. O validador de links não detecta
contradições de conteúdo nem comprova que comandos documentados funcionam.

## Cobertura dos requisitos

“Contemplado” abaixo significa que a implementação e as verificações examinadas
cobrem o comportamento indicado; não significa certificação de ausência de bugs.

| Item | Situação e evidência / falta |
| --- | --- |
| Task 2.1 — SQLAlchemy/PostgreSQL/Alembic | Contemplada: schema, migrações 0001–0003, adoção do legado e testes; 42 testes em PostgreSQL nesta auditoria. |
| Task 2.2 — rotas e validação | Parcial: modelos de sucesso e validação presentes; corrigir contrato de erros A07. |
| Task 2.3 — quatro leituras | Contemplada na base literal: processo/inventário, filtro de busca, páginas e requisitos. Recuperação semântica permanece externa. |
| Task 2.4 — duas escritas idempotentes | Contemplada para efeitos: transação, unique constraint, replay/conflito, rollback e leitura independente. Auditoria das tentativas é incompleta, A03. |
| Task 2.5 — runs e contexto autenticado | Parcial: criação, claim, lease, permissões e encerramento presentes; corrigir A01–A05. |
| B01 — seis tools comuns | Presentes; schemas de argumentos excluem contexto privilegiado. Erros OpenAPI incompletos, A07. |
| B02 — corpus, fontes, páginas e limites | Contemplado no corpus sintético: filtros antes do limite, referências resolvidas e aviso de cobertura. Qualidade factual depende dos agentes/RAG/Metodologia. |
| B03 — checklist versionado | Contemplado tecnicamente: importação administrativa, imutabilidade e validação de requirement_id. Homologação institucional pendente externa. |
| B04 — escrita confirmada | Contemplado para persistência/idempotência; não equivale a validação semântica ou confirmação independente científica. |
| B05 — contexto/autorização | Contemplado nos fluxos examinados: duas credenciais, lease, perfil e concessões por processo/corpus. Marcador de participante não é autenticação. |
| B06 — persistência/recuperação | Migrações e concorrência testadas novamente em PostgreSQL. Há relatório/dump de restart/restore anterior, das 12 tabelas, inspecionados; essa operação não foi repetida nesta auditoria. |
| B07 — chat/memória | Parcial: memória de sucessos e exclusão de falhas testadas; agregado pode ocultar resposta, A02, e falha sem deltas é omitida, A06. |
| B08 — acompanhamento e reconexão | Parcial: eventos persistidos e validação de resposta final presentes; snapshot SQLite viola reconexão, A01; agregado inconsistente, A02. |
| B09 — participante/exportação | Marcador, filtros, ausência no contexto e exportação sem textos por padrão contemplados. Registro de chamadas exportado incompleto, A03. |
| B10 — agentes reais | Não atendido ainda; dependência externa explicitamente assumida no PRD. Doubles/simulador não satisfazem o aceite. |
| PRD, TDD e ADRs | Artefatos existem e delimitam escopo/dependências; afirmação de desenho implementado precisa considerar os defeitos confirmados. |

## Verificações desta auditoria

- `uv run --locked python -m scripts.dev check`: lint, formato, links/invariantes
  aprovados; **42 testes aprovados em SQLite**, um aviso Starlette/HTTPX.
- `uv run --locked python -m pytest` com `TEST_DATABASE_URL` privado em
  PostgreSQL 17 dedicado: **42 testes aprovados**, mesmo aviso.
- Provas negativas adicionais: A01–A04 em banco temporário/MockTransport pelo
  revisor CTO; A02 também reproduzido nesta auditoria em PostgreSQL; A05–A07
  por requisições ASGI em banco temporário. Nenhum documento real utilizado.
- Reprodução local dos quatro cenários CTO:
  `uv run --locked python data/audit_cto_probes.py` — exit 0, quatro defeitos
  reproduzidos. O script de diagnóstico está em `data/`, ignorado pelo Git;
  usa SQLite temporário e não acessa credenciais ou banco existentes.
- Portal: lint e TypeScript verificados; a inspeção do código constatou A02/A06.
  O build de produção existente e seu registro anterior foram inspecionados;
  build, navegador, Nginx, imagens completas e implantação não foram repetidos.
  O lint mantém o aviso preexistente de `img` em `portal/app/team/page.tsx:150`.
- A suíte atual não contém as regressões dos defeitos reproduzidos. Os 42 testes
  verdes comprovam seus cenários, não esses interleavings ou a completude da auditoria.
- O container PostgreSQL exclusivo de validação foi iniciado para os testes e
  parado ao final; dados e dumps preservados. Nenhuma alteração remota.

## O que falta para aceite

Prioridade técnica: corrigir A01/A02; completar histórico de tentativas A03;
tratar indisponibilidade no worker A04; fechar validação de registros A05;
apresentar impedimentos no chat A06; alinhar OpenAPI A07 e instruções A08.
Cada correção deve incluir regressão do cenário descrito, seguida da suíte
nos dois bancos e da jornada real do portal com envio, reconexão e artefatos.

Aceites externos: runtime/URL/versão oficial do Hermes, adaptadores reais de
ambos os executores, modelo/endpoint autorizado, corpus e checklists homologados,
e revisão conjunta dos contratos. Autenticação individual e infraestrutura
remota são gates para compartilhamento; upload, OCR, embeddings, cache e painel
comparativo não são lacunas da entrega local de backend acordada.

Este relatório conclui a auditoria; não declara as correções implementadas
nem o piloto completo homologado.

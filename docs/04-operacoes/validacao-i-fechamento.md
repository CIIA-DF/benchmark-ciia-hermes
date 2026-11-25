# Relatório completo do bloco I — Integrações

Data: 31/10/2026. Estado: fechamento técnico local I1–I3 concluído, disponível para liberação manual do responsável.
Worktree: `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`. Branch: `team/backend`.
Escopo: I1, I2 e I3 do [plano](../02-arquitetura/backend-plano-blocos.md), com dados sintéticos e SQLite.
Revisão CTO/Astra e liberação do responsável permanecem manuais.

## Aceites individuais

| Sub-bloco | Resultado | Seleção dirigida final | Evidência |
| --- | --- | --- | --- |
| I1 | Clientes síncrono/assíncrono preservam requisição e não duplicam efeito em retry | 36 aprovados; 133,97 s | [I1](validacao-i1.md) |
| I2 | Bootstrap só cria ausentes; administração e rotação explícitas; revogação sobrevive ao reinício | 26 aprovados; 51,29 s | [I2](validacao-i2.md) |
| I3 | Limites, prazos, cabeçalhos, SSE e cancelamento seguros no proxy | 29 aprovados; 135,95 s | [I3](validacao-i3.md) |

I1 foi fechado antes de I2, e I2 antes de iniciar I3. A conferência final encontrou uma lacuna no erro de conexão do CLI I2.
Ela foi reproduzida, corrigida e submetida novamente ao aceite dirigido I2, sem repetir a suíte completa.
Os 19 casos próprios I3 também passaram na versão final das sondas, em 8,67 s, sem skips.
As seleções incluem regressões próximas e têm interseção; não somar seus números como tamanho da suíte.

## Contratos e consumidores

Os seis contratos de tools e os envelopes HTTP do backend preservam os campos funcionais existentes.
I1 afeta ToolClient, AsyncToolClient e os adaptadores que os consomem. Não instala adaptador real nem altera a política de seleção de ferramentas.
I2 afeta inicialização, scripts.provision e autenticação de operações de worker. Migração aditiva 0009 cria administrative_events.
I3 afeta ModelConfig, a rota proxy Next, os exemplos de ambiente e os perfis Compose/Nginx.
As alterações editoriais de contratos feitas em paralelo não constituem conclusão do bloco D.

| Dado comum | Origem confiável | Destino e garantia |
| --- | --- | --- |
| run_id/process_id/corpus_version/requirements_version | Execução reservada no servidor | Contexto das seis tools; validação da resposta contra a cópia capturada |
| Token do worker e X-Run-Token | Configuração privada e claim | Autenticação técnica e lease; não vêm do conteúdo gerado pelo modelo |
| X-Tool-Call-Id | Cliente, uma vez por chamada lógica | Retry mantém ID e bytes; servidor registra tentativas físicas separadas |
| idempotency_key | Entrada explícita da escrita | Mantida junto do conteúdo; recuperação do mesmo artefato após perda de resposta |
| artifact_id/content_sha256/persisted_at/replayed | Recibo do efeito persistido | Validação de saída, acompanhamento e GET de artefato autorizado |
| Last-Event-ID/cursor de eventos | Acompanhamento do operador | Proxy preserva retomada; evento transmitido não prova recebimento pelo usuário |
| Perfil/grants atuais | Banco e operação administrativa | Bootstrap não sobrescreve; rotação preserva permissões atuais |

## Workflow registrado

1. Bootstrap cria identidades ausentes. Uma alteração de perfil ou rotação exige operação administrativa explícita.
2. Worker autenticado reserva a execução e recebe contexto e lease. O agente escolhe quais ferramentas chamar.
3. Cliente captura contexto, argumentos aninhados e requisição HTTP antes do primeiro envio.
4. Backend admite a tentativa física, valida autorização/contexto e vincula o ID lógico à operação antes do efeito.
5. Leituras retornam processo, inventário, trechos, documento ou checklist. Escritas usam referências verificáveis e permissões atuais.
6. Persistência confirma artefato e recibo. Perda do retorno permite retry com a mesma requisição e chave, recuperando o efeito.
7. Cliente valida saída estruturada contra o contexto e a entrada capturados. Sucesso inválido não é repetido automaticamente.
8. Resultado declarado pelo adaptador continua sujeito à reconciliação do backend; não substitui o histórico observado.
9. Operador acompanha o run por HTTP/SSE e consulta artefatos sob sua autorização. Proxy usa a credencial do servidor e preserva cursores.

Não há cadeia obrigatória entre as seis tools. Chamadas independentes continuam paralelizáveis quando autorizadas.
As relações de dados continuam as mesmas: inventário e trechos fundamentam escritas; checklist versionado identifica o requisito de uma pendência.
A minuta pode seguir jornada sem checklist conforme F6; I não impõe uma consulta prévia artificial.

## Falhas, autenticação e transporte

| Fronteira | Comportamento |
| --- | --- |
| Credencial antiga após rotação | Nova autenticação recebe 401; ambiente antigo não restaura o token |
| Rotação entre reserva lógica e efeito | Revalidação recusa com 403 e não cria artefato |
| Grant ou can_write revogado | Reinício/setup não restaura o privilégio; operação continua recusada |
| Conflito de contrato/idempotência | Mantém erro estruturado e não duplica efeito |
| Quota definitiva | Mantém recusa; sinalizador incoerente não força retry de status definitivo |
| Timeout/erro transitório de tool | Até três tentativas existentes, com o mesmo ID, corpo e chave |
| Sucesso HTTP com saída inválida | Erro no cliente, sem retry automático ou recibo inventado |
| Corpo do proxy acima de 1 MiB | 413 payload_too_large contando bytes, mesmo com tamanho declarado menor |
| Leitura de corpo do proxy excede o prazo | 408 request_timeout e cancelamento da leitura |
| Proxy sem configuração válida | 503 proxy_unavailable seguro |
| Falha antes dos cabeçalhos upstream | 503 upstream_timeout ou upstream_unavailable |
| Falha após abertura de SSE | Status original preservado; stream_error seguro, com encerramento e cancelamento upstream |

Códigos locais do proxy têm message/code; não mudam ToolError do backend.
O Nginx pode rejeitar antes do Next com sua resposta nativa de 413/408; esse corpo não foi padronizado como JSON nem homologado nesta rodada.
Prazos padrão do Next: 20 s por fase de corpo/cabeçalhos e 30 s de inatividade da resposta, sem teto total de SSE.
Nginx mantém limites independentes e buffering desativado. [Catálogo detalhado I3](validacao-i3.md).

## Validação consolidada

O comando oficial `uv run --locked python -m scripts.dev check`, já iniciado por outra tarefa nesta mesma worktree, terminou com **código 0**.
Foi acompanhado até o encerramento e seu log copiado para tmp/i-shared-check.log, sem iniciar uma segunda suíte concorrente.
Metadados em tmp/i-shared-check-metadata.json: início em 31/10/2026 às 16:52:50 (-03:00), encerramento observado às 17:21:40 (-03:00).
Tempo observado do comando: **1729.94 s**, incluindo lint, formatação, validação do repositório e pytest.

Resultado integral observado: **454 testes aprovados em SQLite em 1.640,62 s (27min20s)**, com um aviso Starlette/HTTPX já existente.
Lint e formatação dos 220 arquivos da coleta original, links, YAML e invariantes também passaram.
O processo foi anexado antes do término; o código de saída 0 foi capturado diretamente, não inferido apenas dos pontos de progresso.

A suíte compartilhada começou antes dos últimos acréscimos I2/I3. A coleta final contém **458 casos**.
Os quatro casos adicionais são as três falhas de criação de conexão do CLI I2 e o timeout de leitura do corpo do proxy I3.
Eles passaram nas seleções dirigidas finais de 26 e 19 casos, respectivamente, sem skips nesta máquina.
Isso registra 454 casos na execução integral e quatro casos novos cobertos por complemento dirigido.
Não houve uma execução única de 458 casos nem uma segunda execução integral após o último ajuste do CLI.
O fechamento usa a suíte compartilhada mais a regressão dirigida do delta; não apresenta a execução anterior como teste integral da última revisão do CLI.
Os totais dos dirigidos não devem ser somados à suíte, pois a maioria dos casos se repete.

Após os últimos ajustes, lint/formatação dos nove arquivos Python do bloco I passaram novamente.
Lint Next da rota e `tsc --noEmit --incremental false` terminaram com código 0, log tmp/i3-portal-check.log.
OpenAPI, links/invariantes e whitespace também foram conferidos na versão final.
Manifesto tmp/i-source-manifest.json registra hashes dos arquivos de código/configuração/testes I; nenhuma alteração desses arquivos ocorreu desde a conferência final.

Os tempos não isolam desempenho do backend: havia tarefas concorrentes na máquina e a suíte envolve preparação/migrações de bancos sintéticos.
Não foi atribuído ganho ou regressão de produto às diferenças de duração. Aproveitar a execução compartilhada evitou repetir mais 454 testes.

## Limites e próximos blocos

PostgreSQL não foi executado: Docker Linux indisponível nesta máquina. Travas consultivas e concorrência PostgreSQL continuam para H.
Nginx foi conferido estaticamente; sem executável local nem stack Compose disponível para comprovar a cadeia completa.
Sondas HTTP/streams do Node executam a rota real com pares sintéticos. Não comprovam aplicação Next implantada ou inferência real.
Na suíte Python, as 13 sondas de rota têm skip explícito se Node/Next/TypeScript não estiverem instalados; nesta worktree foram executadas.
A CI Python atual não instala o portal e não deve ser citada como prova dessas sondas sem preparar as dependências.
Não houve mudança de dependências nem migração da base operacional. Migração/downgrade 0009 foram verificados apenas em bancos sintéticos.
Backup/restauração precisa incluir a nova trilha administrativa em H. A trilha não prova identidade humana nem é resistente ao administrador do banco.

Permanecem pendentes **D, E, O e H**: documentação formal, exportação canônica, observabilidade e homologação.
Relatórios incrementais e docstrings não encerram D. Nenhum ganho de custo, latência ou qualidade de LLM foi demonstrado.
Alterações de outras tarefas na worktree, inclusive backlog e revisão A7, foram preservadas; seus aceites não são substituídos por este relatório.
Sem commit, push, PR, deploy ou revisão automática CTO/Astra nesta execução do objetivo I.

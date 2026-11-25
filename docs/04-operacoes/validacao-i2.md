# I2 — Identidades administrativas e reinício seguro

Data: 31/10/2026. Worktree C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes, branch team/backend.
Escopo: I2 do [plano](../02-arquitetura/backend-plano-blocos.md). Sem publicação.

## Achado e implementação

Bootstrap restaurava can_write e grants de perfis já revogados. Reprodução anterior: 8,12 s, tmp/i2-before.log.
Agora só cria principais ausentes. Perfil existente é preservado por completo, mesmo com variável antiga ou token diferente no ambiente.
Reiniciar não rotaciona credenciais nem recupera privilégios. Repetir setup preserva arquivos privados; mudanças exigem administração explícita.

scripts.provision mantém criação como padrão e recusa perfil existente. --operation update exige perfil/concessões explícitos e não cria identidade ausente.
--operation rotate aceita apenas principal_id/token_env e muda somente a credencial: papel, executor, can_write e grants atuais permanecem.
A entrada privada tem modelos fechados, booleanos estritos e referências a variáveis de ambiente, sem token literal no JSON.
Erros do comando saem com código 2 e mensagem segura, sem ecoar payload, credencial ou SQL.
Os exemplos e a mudança do comportamento anterior estão em [chat](chat.md#perfis-e-permissões) e scripts/README.md.
A função Python provision continua sendo operação administrativa explícita de substituição completa; bootstrap usa create_only.

## Atomicidade, auditoria e revogação

Migração aditiva 0009 cria administrative_events: ID, principal, operação, origem de código, instante, estados de permissões e credential_changed.
Não guarda token, hash de token, cabeçalho ou conteúdo de documentos. Origem admin/bootstrap não atesta identidade humana.
Sem backfill de atos antigos. O downgrade de 0009 remove a tabela nova e sua trilha; exige backup antes de uso administrativo. Atualização, rotação, grants e evento de auditoria confirmam juntos; falha no evento desfaz a operação.
Bootstrap repetido não inventa eventos de alteração quando nada muda. Dois criadores concorrentes produzem uma identidade e um evento.
SQLite usa BEGIN IMMEDIATE; PostgreSQL tem trava consultiva por identidade para criação e trava de perfil para operações existentes.
O caminho PostgreSQL é implementação a homologar no bloco H, não evidência de execução nesse banco.

Operações de worker releem papel, executor e hash atual da credencial após obter a trava do run.
Escritas revalidam a credencial também sob as travas de perfil na transação do efeito.
Uma rotação entre reserva lógica e escrita recusa o ator antigo com 403 e não grava artefato.
Novas requisições com token antigo recebem 401. A rotação não altera por si só grants, orçamento, histórico ou a lease existente.
Clientes autorizados precisam receber o novo segredo por configuração privada; o comando não reescreve arquivos privados dos clientes automaticamente.
Não há endpoint administrativo público nem mudança nos DTOs HTTP. OpenAPI permanece consistente.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/backend/test_i2.py tests/backend/test_t0_r1.py tests/backend/test_a7.py::test_stale_identity_cannot_refresh_lease_or_presence --durations=5
```

**23 casos distintos aprovados em SQLite em 7,49 s**, log tmp/i2-directed.log.
Treze próprios cobrem revogação seguida de nova aplicação/engine, rotação de operador/worker com ambiente antigo,
criação concorrente, rollback de update/rotate por falha de auditoria, operações CLI explícitas,
três configurações inválidas sem eco de segredo, migração sem backfill, credencial rotacionada entre reserva/efeito e repetição real de setup.
Dez regressões próximas conferem revogação sob trava e identidade atual no heartbeat.
A primeira seleção de 22 casos passou em 60,81 s; foi acrescentada a prova de setup e repetida a seleção final, sem somar repetições.
A prova isolada de setup também passou. Ela usa diretórios/ambiente sintéticos e não toca data/chat.env ou portal/.env.local operacionais.
Variáveis inicialmente ausentes também são restauradas pelo teste, sem vazar configuração para os próximos casos.
Diferenças de duração não isolam causa de desempenho. Aviso Starlette/HTTPX existente permanece.

Lint/formato dos arquivos alterados, OpenAPI, links/invariantes e whitespace verificados.
Aceite I2 comprovado localmente. Suíte completa reservada ao fechamento I.
Migração/downgrade só em bancos sintéticos; base operacional não foi migrada. Backup/restauração da nova trilha entra no bloco H.
PostgreSQL, execução entre hosts e revisão manual CTO/Astra pendentes. Alteração preexistente do backlog preservada.
Sem commit, push, PR, deploy ou revisão automática.


## Complemento do aceite — erro ao criar a conexão

A conferência final identificou make_engine fora do tratamento seguro do CLI.
Três sondas reproduziram exceções com detalhes privados em vez da saída segura: ValueError, SQLAlchemyError e OSError.
A criação da conexão agora ocorre dentro do try; dispose só executa quando o engine existe.
Falhas de conexão/configuração/arquivo retornam código 2 com mensagem genérica, sem os detalhes da exceção.
Evidência anterior: tmp/i2-cli-before.log, três falhas esperadas em 4,89 s.

A seleção dirigida acima foi repetida na versão corrigida: **26 casos distintos aprovados em 51,29 s**, tmp/i2-final-directed.log.
São 16 próprios e dez próximos. Os três novos casos complementam os 23 anteriores; repetições não aumentam o total.
Lint e formatação dos dois arquivos afetados passaram. Esse complemento substitui a contagem anterior como aceite dirigido final I2.

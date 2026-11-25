# Executar o chat experimental

O chat usa as seis tools comuns, preserva o histórico e transmite a resposta
por eventos SSE. O executor inicial é uma simulação explícita: consulta os
documentos fictícios e demonstra o protocolo, sem chamar uma LLM.

## Inicialização com PostgreSQL

Requisitos: Git, uv, Docker Desktop com o motor Linux ativo e acesso à rede
para baixar dependências e imagens. Execute na raiz do repositório:

```powershell
uv sync --locked
uv run --locked python -m scripts.chat setup
uv run --locked python -m scripts.chat up
```

Abra `http://localhost:3000/chat`. A stack inclui PostgreSQL 17, FastAPI,
worker simulado e portal Next.js. O corpus e o checklist carregados são
exclusivamente fictícios. Apenas portal e API publicam portas em loopback;
o banco permanece na rede interna.

O setup gera credenciais aleatórias em `data/chat.env` e configura o proxy
do portal em `portal/.env.local`, ambos ignorados pelo Git. Reexecutá-lo
preserva esses arquivos. Caso já exista configuração do portal, confira
privadamente se ela aponta para o mesmo backend e operador.

Para encerrar, preservando o volume do banco:

```powershell
uv run --locked python -m scripts.chat down
```

O projeto Compose local usa um nome próprio para preservar outras stacks.
Não use remoção de volumes para resolver falhas de senha ou migração.

## Prévia sem Docker

SQLite permite uma prévia com um worker. Esta prévia não comprova o
comportamento concorrente do PostgreSQL.

Após o setup, abra terminais separados na raiz:

```powershell
uv run --locked python -m scripts.chat serve
```

```powershell
uv run --locked python -m scripts.chat worker
```

No diretório `portal`, execute:

```powershell
npm ci
npm run dev -- --hostname 127.0.0.1
```

Abra `http://127.0.0.1:3000/chat`. O comando `serve` prepara a fixture
sintética e o checklist no banco local. O worker recebe as credenciais pelo
lançador; nenhuma chave deve ser copiada para o código do navegador.

## Uso do chat

1. Selecione um processo e um executor disponível.
2. Envie a pergunta e acompanhe o estado e os trechos da resposta.
3. Expanda **Fontes** para conferir documento, página e chunk.
4. Envie uma pergunta de continuidade para usar o histórico concluído.
5. Use **Nova conversa** para trocar processo, versão ou executor.

Fechar a aba não cancela a execução. Ao reabrir a conversa, o portal
recupera o texto e um cursor consistente, retomando os eventos seguintes.
Mensagens parciais e falhas permanecem consultáveis, mas não entram no
contexto das próximas perguntas. O limite de contexto gera erro explícito.

O navegador armazena somente o identificador da última conversa. Textos,
fontes e eventos ficam no banco; credenciais ficam no servidor.

## Perfis e permissões

O piloto tem um operador local e um worker de simulação. Cada credencial
tem somente seu hash SHA-256 persistido. As concessões são explícitas por
processo e corpus, sem permissão curinga.

Para outros perfis, crie um JSON privado fora do Git, por exemplo:

```json
[
  {
    "principal_id": "worker-langgraph",
    "token_env": "LANGGRAPH_WORKER_TOKEN",
    "role": "worker",
    "executor": "langgraph",
    "can_write": true,
    "grants": [
      {"process_id": "PROC-DEMO-001", "corpus_version": "synthetic-v1"}
    ]
  }
]
```

Configure a variável com um token aleatório de pelo menos 32 caracteres e
execute `uv run --locked python -m scripts.provision CAMINHO_PRIVADO`.
A aplicação deve usar a mesma `DATABASE_URL`. O padrão é **create**: identidade existente é recusada, sem substituir concessões.
Para atualizar um perfil existente, use `--operation update` com role, executor quando worker, can_write e grants explícitos.
Essa operação substitui o perfil/concessões na mesma transação de sua auditoria; não altera o corpus.
Em create e update, `can_write` é obrigatório como role e grants: omiti-lo não revoga mais a escrita em silêncio. Um arquivo com vários perfis é conferido inteiro antes da primeira escrita (desde 21/11/2026): as regras de perfil (worker com executor, operador sem executor, token com 32 ou mais caracteres); a existência (em create, nenhum pode existir; em update e rotate, todos precisam existir); e a credencial (`principal_id` ou token repetido no arquivo, ou token que já pertence a outro perfil no banco, é recusado). Se algo falhar no meio (por exemplo, outro processo criou o perfil depois da conferência), a mensagem informa só a contagem, "Perfis aplicados: k de n", sem identificar perfis.

Para rotacionar somente a credencial, use outro JSON privado mínimo:

```json
[{"principal_id": "worker-langgraph", "token_env": "LANGGRAPH_WORKER_TOKEN"}]
```

Execute `uv run --locked python -m scripts.provision CAMINHO_PRIVADO --operation rotate`.
Role, executor, can_write e concessões atuais são preservados, inclusive revogações. Campos de perfil no arquivo de rotação são recusados.
O token antigo deixa de autenticar. Atualize também os arquivos privados/variáveis dos clientes autorizados; não publique tokens em comando ou Git.
O bootstrap só cria principais ausentes: mudar variáveis e reiniciar não rotaciona credenciais nem restaura direitos revogados.
Se o token do ambiente difere do perfil local gravado, o backend registra o aviso `bootstrap_token_mismatch principal_id=…` (sem token nem hash) e mantém o perfil; o portal e o worker com esse token recebem 401 até a rotação explícita.
Repetir scripts.chat setup preserva arquivos privados existentes; mudanças de direitos/credenciais exigem a operação administrativa explícita.
A migração 0009 guarda operação, origem de código, estados de permissões e indicação de troca de credencial, sem token ou hash de token.
A origem do código não comprova identidade humana; acesso ao comando/banco depende da administração do ambiente.
Falha ao registrar essa auditoria desfaz a mudança administrativa. A trilha anterior à migração não é inventada retroativamente.

O worker recebe uma segunda credencial temporária na reserva da execução.
Todas as tools exigem tanto o token de serviço quanto `X-Run-Token`.
O servidor confere contexto, reserva ativa e concessões atuais do worker
e do proprietário. Escritas exigem `can_write` em ambos os perfis.

## Checklist e ferramentas de escrita

Importe checklists homologados administrativamente:

```powershell
uv run --locked python -m scripts.checklist CAMINHO_PRIVADO --process PROCESSO --corpus VERSAO --version REQUISITOS
```

A versão deve corresponder ao processo/corpus. Uma versão já preenchida é
imutável. A fixture `demo-v1` é sintética e não comprova homologação.

Pendências exigem `requirement_id`; ambas as escritas exigem referências
válidas e `evidence_note`. Para ausência documental, use referência de
inventário e registre os limites de cobertura. Busca vazia não comprova
ausência no processo original.

Repetir a mesma operação, com a mesma chave e entrada, devolve o recibo
original com `replayed=true`. Alterar a entrada com a mesma chave gera
`409`. Consulte `GET /artifacts/{artifact_id}` como operador para conferir
conteúdo e hash de uma gravação confirmada.

## Migrações e recuperação

Alembic substitui `create_all` na inicialização. A revisão `0001` representa
o corpus original; `0002` acrescenta conversas, execuções e ferramentas.
Um banco legado só recebe o marcador inicial após comparação do schema.
Estruturas divergentes interrompem a inicialização.

Faça backup antes de atualizar um banco existente. Para migração explícita:

```powershell
uv run --locked python -m scripts.migrate upgrade head
```

O downgrade para `0001` remove os dados de conversas, perfis e artefatos.
Use-o somente em cópia de desenvolvimento ou após backup validado:

```powershell
uv run --locked python -m scripts.migrate downgrade 0001
```

Para rollback operacional com preservação de histórico, restaure o backup
em banco separado e execute a versão de aplicação correspondente.
Consulte [backup e restauração](backup-restore.md).

## Integração e infraestrutura

Os adaptadores das equipes implementam `AgentAdapter.stream`, consumindo
`ClaimedRun` e `AsyncToolClient`. Consulte o
[contrato de integração](../../contracts/README.md). Habilite executores
em `ENABLED_EXECUTORS` somente depois de provisionar e validar seus workers.
O streaming real depende dos eventos disponibilizados pelo modelo/adaptador.

O proxy do portal representa um único operador e bloqueia hosts remotos.
Antes de compartilhar o chat na VPS, a Infra deve integrar autenticação
individual e vincular cada sessão a seu perfil. Não remova essa restrição
para publicar uma credencial compartilhada. O deploy anterior do portal
de documentação não implementa essa identidade.

O exemplo `infra/nginx-chat.conf` permite conferir o streaming por proxy
local. Desative buffering e cache na rota SSE e preserve o cursor
`Last-Event-ID`. Conexão do navegador e vida da execução são independentes.

Registre em logs somente IDs, estados, duração e versões. Prompts,
documentos, tokens e credenciais não pertencem aos logs operacionais.

## Verificações

```powershell
uv run --locked python -m scripts.dev check
uv run --locked python -m scripts.dev demo
```

Em `portal`, execute `npm run lint`, `npx tsc --noEmit` e `npm run build`.
Os testes usam SQLite por padrão. Defina `TEST_DATABASE_URL` para um banco
PostgreSQL exclusivo de testes para validar concorrência real. Nunca use
um banco com corpus real ou resultados finais.

Execuções do chat têm `kind=chat`. Execuções de benchmark têm
`kind=benchmark`, histórico isolado e registro `ExperimentRun` obrigatório
para conclusão bem-sucedida. O worker não pode declarar sucesso verificado
nem identidade de avaliador; essa atribuição pertence à Metodologia.


## Participantes e artefatos

O piloto local não exige login. O navegador gera um UUID pseudônimo em
localStorage; ele permanece associado à conversa e organiza a lista de histórico.
Não use nomes, e-mails ou matrícula como marcador. O filtro não protege conversas
contra outro participante que use o mesmo operador técnico. Limpar armazenamento
ou usar outro navegador gera outro marcador. Conversas antigas continuam com null.

Cada run devolve os artefatos gravados. No chat, use **Conferir conteúdo e recibo**
para consultar conteúdo, fundamentação, data e hash diretamente da API. Uma falha
posterior do agente não desfaz automaticamente artefatos já confirmados.

A migração 0003 acrescenta o marcador sem alterar o corpus. Identidades técnicas
continuam obrigatórias entre servidor e workers, invisíveis ao participante.

## Exportação privada para Evaluation

Configure DATABASE_URL privadamente para o banco pretendido. Crie um diretório
results ignorado pelo Git e escolha um nome de saída ainda inexistente:

```powershell
uv run --locked python -m scripts.export_chat --output results/chat.jsonl
```

Formato atual: **export_version 2**, com dados declarados, observados e avaliados separados.
Tentativas/fases vêm do histórico persistido, inclusive falhas tardias; SSE não é a fonte de contagem.
Filtros: --participant UUID, --conversation UUID e --run UUID. Padrão --kind chat;
use --kind benchmark ou --kind all para incluir execuções sem conversa.
Conteúdo e parâmetros livres exigem --include-content. Desconhecidos continuam null.
Arquivo final só é publicado quando completo, sem sobrescrever destino; o volume precisa permitir hard links.
[Contrato v2, migração do consumidor, privacidade e limites](exportacao-canonica.md).

## Backup da stack de chat

Os argumentos identificam explicitamente a stack para não atingir outro banco:

```powershell
uv run --locked python -m scripts.database_backup backup backups/chat.dump --env-file data/chat.env --project-name ciia-chat-local
uv run --locked python -m scripts.database_backup restore-test backups/chat.dump --env-file data/chat.env --project-name ciia-chat-local
```

A restauração usa banco novo e inclui contagens de conversas, mensagens, runs,
eventos e artefatos. Conferir também conteúdo/hash e consultas na cópia; contagem
sozinha não comprova integridade. Não remover volumes para resolver falhas.

Integrações reais: [handoff para as equipes](integracao-agentes.md).


## Demonstrar as seis tools antes dos agentes

```powershell
uv run --locked python -m scripts.tools_demo
```

Este comando prepara somente corpus sintético, cria uma execução técnica e
exercita as quatro leituras e as duas escritas. Confere replay e hash por uma
leitura independente. Imprime apenas IDs e resultados de verificação, sem tokens.
Não usa LLM e não é resultado científico. Sem DATABASE_URL, usa data/demo.db.


## I3 — Prazos e limites do proxy local

O portal aceita corpo de até 1 MiB contando bytes recebidos. BACKEND_PROXY_TIMEOUT_SECONDS (padrão 20) limita a leitura total do corpo e a espera dos cabeçalhos do backend, por fase.
BACKEND_PROXY_IDLE_TIMEOUT_SECONDS (padrão 30) limita inatividade da resposta; não limita a duração total do SSE.
Valor vazio ou só com espaços usa o padrão, como `${VAR:-20}` no Compose; `0`, negativo ou não finito continua recusado com 503.
Os dois valores exigem segundos positivos e finitos. Compose os passa ao portal; fora dele, configure o ambiente do processo Next.
Corpo lento retorna 408 request_timeout; excesso retorna 413 payload_too_large.
Falha de transporte anterior aos cabeçalhos retorna 503; em SSE aberto, stream_error informa interrupção sem alterar o status já enviado.
Credenciais continuam somente no servidor. Este proxy representa um operador local e não fornece autenticação multiusuário.
[Catálogo de códigos, encaminhamento e evidências I3](validacao-i3.md).

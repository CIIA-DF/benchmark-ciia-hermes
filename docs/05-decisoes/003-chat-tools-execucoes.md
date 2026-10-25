# ADR 003 — chat, tools e execuções persistentes

Data: 20/10/2026, America/Sao_Paulo.
Estado: implementação local para revisão das equipes afetadas.
Responsável: Backend & Tools, Roger Quinelato.

## Contexto e decisão

O backend precisa oferecer as mesmas seis tools a Hermes e LangGraph e
receber tarefas de um chat com memória e resposta progressiva. A decisão
mantém a stack existente e usa PostgreSQL como fila persistente, com
reservas transacionais e SSE para acompanhar o andamento.

Conversas são vinculadas a processo, versões e executor. Cada pergunta
gera um run e um snapshot de contexto. Execuções de benchmark têm histórico
isolado e registro experimental obrigatório ao concluir com sucesso.

Os workers consomem HTTP e implementam um protocolo comum de eventos e
resultado. O backend confere contexto autenticado e permissões atuais;
as equipes dos agentes continuam responsáveis pelo raciocínio e inferência.
O simulador valida o fluxo sem se apresentar como agente real.

## Consequências

Migrações Alembic precedem mudanças de schema. Escritas usam referência
validada, transação e chave única no banco. Eventos confirmados no banco
podem ser retomados depois de perda da conexão. A expiração da reserva
preserva o parcial e encerra a execução, sem reexecutar efeitos automaticamente.

O proxy inicial do portal representa um operador local e bloqueia hosts
remotos. Compartilhamento na VPS depende de autenticação individual e da
associação de cada sessão ao perfil correspondente pela Infra.

## Alternativas consideradas

Requisição HTTP mantida até a conclusão simplifica o primeiro exemplo,
mas acopla a vida da tarefa à conexão. Um broker dedicado aumenta o número
de serviços sem necessidade demonstrada no piloto. A fila no PostgreSQL
reutiliza persistência e transações já previstas pelo projeto.

## Aceite

Validar memória, isolamento do benchmark, streaming e reconexão,
idempotência, concorrência, rollback e preservação dos dados após reinício.
Registrar resultados efetivamente observados no status do projeto.
Consultar [contratos](../../contracts/README.md) e
[operação](../04-operacoes/chat.md) antes de integrar adaptadores reais.

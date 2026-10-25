# ADR 005 — participante pseudônimo no piloto sem login

Data: 24/10/2026. Estado: decidido pelo responsável, implementado localmente.

## Contexto e decisão

O piloto é usado pelo time interno e precisa relacionar conversas à análise de
Evaluation sem exigir contas pessoais. O navegador gera participant_id UUID;
a conversa o persiste como metadado. Ele não entra no contexto do modelo.

Tokens de operador/worker e reserva continuam no servidor. O marcador não é
credencial, não concede permissão e não identifica uma pessoa de forma verificada.
Filtrar conversas pelo marcador organiza a interface; não cria isolamento.
Sem marcador, conversas legadas continuam válidas com null.

## Alternativas e consequências

Login/SSO agora exigiria uma integração de identidade fora do piloto local.
Remover autenticação das tools permitiria ampliar contexto e efeitos de escrita.
A opção mantém UI sem login e autorização técnica obrigatória.

Limpar armazenamento do navegador gera outra identificação. Compartilhar navegador
compartilha marcador. Acesso remoto/multiusuário exige integração de identidade
pela Infra antes de remover a restrição a loopback.

Exportação privada para Evaluation inclui marcador e IDs; conteúdo textual só
com opção explícita. Não interpretar marcadores como contagem validada de pessoas.

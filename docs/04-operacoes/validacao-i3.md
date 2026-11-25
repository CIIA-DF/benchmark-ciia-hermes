# Relatório completo do I3 — Transporte e ambiente de execução

Data: 31/10/2026. Worktree: `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend`.
Escopo: conexão, proxy do portal, limites, cabeçalhos e SSE. Dados e credenciais dos testes são sintéticos.

## Diagnóstico e alterações

A sonda inicial mostrou que o proxy consumia dez chunks de 400.000 bytes antes de rejeitar o corpo.
O cliente de modelo também aceitava timeout `nan`. Evidências: tmp/i3-before.log e tmp/i3-timeout-before.log.

O proxy agora conta bytes durante a leitura, aceita até 1.048.576 bytes e interrompe excesso mesmo com Content-Length menor que o corpo.
A leitura total do corpo tem prazo; timeout retorna 408, excesso retorna 413 e erro de leitura retorna 400.
A configuração é validada antes da leitura. URL do backend exige HTTP/HTTPS, sem usuário, senha, query ou fragmento.
Timeouts do proxy precisam ser positivos, finitos e compatíveis com o timer do Node.
ModelConfig também rejeita timeout não finito ou não positivo.

O proxy continua representando um operador local, com allowlist de rotas e verificação de Host, Origin e Sec-Fetch-Site.
A credencial vem somente do ambiente do servidor. Authorization, Cookie, X-Run-Token e X-Forwarded-For do navegador não são encaminhados.
Last-Event-ID e query de cursor são preservados. Respostas preservam status, Content-Type, WWW-Authenticate, Allow e Retry-After.
Cache-Control permanece no-store e X-Accel-Buffering permanece no. Authorization e Set-Cookie do upstream não são devolvidos.
Redirecionamentos não são seguidos automaticamente.

Leitura SSE repassa chunks antes do evento terminal. Timeout de inatividade e desconexão abortam a chamada upstream.
Um cancelamento concorrente não tenta escrever novamente no stream encerrado.
Falha antes dos cabeçalhos produz HTTP 503 seguro; depois deles, SSE mantém o status original e emite stream_error seguro.
Não há retry automático de mensagens nem de SSE no proxy. Reconexão usa os cursores existentes.
O consumidor atual do portal já trata stream_error reabrindo o acompanhamento a partir de um snapshot consistente, sem alteração de UI nesta etapa.
Erros locais não incluem URL, token ou texto de exceções do transporte. Nenhum log de conteúdo/credenciais foi acrescentado.
Isso não constitui auditoria dos logs de provedores externos.

## Configuração e consumidores

| Parâmetro | Padrão | Semântica |
| --- | --- | --- |
| BACKEND_PROXY_TIMEOUT_SECONDS | 20 s | Prazo total de leitura do corpo e prazo até cabeçalhos do backend, separados por fase |
| BACKEND_PROXY_IDLE_TIMEOUT_SECONDS | 30 s | Inatividade na leitura da resposta; sem teto de duração total para SSE |
| LLM_TIMEOUT_SECONDS | 60 s | Timeout do cliente de modelo, positivo e finito; não comprova conexão com LLM real |

Compose passa os dois parâmetros do proxy ao portal. Fora do Compose, configure-os no ambiente do processo Next.
O exemplo da raiz documenta os padrões; scripts.chat setup não sobrescreve configurações privadas existentes.
O perfil Nginx explicita corpo de 1m, inatividade de corpo de 30s, conexão upstream de 5s, envio de 30s e leitura de 360s.
Mantém HTTP/1.1, buffering/cache desativados, Host original e X-Forwarded-Proto do próprio Nginx.
O limite ASGI do backend continua independente do limite do portal.

### Códigos próprios do proxy

| HTTP | code | Situação |
| --- | --- | --- |
| 404 | not_found | Rota fora da allowlist |
| 403 | forbidden | Host/origem/contexto de navegação recusados |
| 400 | validation_error | Falha ao ler o corpo |
| 408 | request_timeout | Prazo total de leitura do corpo excedido |
| 413 | payload_too_large | Corpo acima de 1 MiB |
| 503 | proxy_unavailable | Segredo ausente ou configuração inválida |
| 503 | upstream_timeout | Backend não respondeu aos cabeçalhos no prazo |
| 503 | upstream_unavailable | Transporte indisponível antes dos cabeçalhos |
| Status já enviado | upstream_timeout ou upstream_unavailable | Evento SSE stream_error após abertura da resposta |

Esses envelopes locais contêm message/code e não substituem ToolError do backend.
Respostas HTTP recebidas do backend mantêm seu status e corpo. Não foi acrescentado código de autenticação próprio ao proxy.

## Evidências e aceite

```sh
uv run --locked python -m pytest tests/integration/test_i3.py tests/backend/test_a0.py::test_actual_asgi_chunk_limit tests/backend/test_a0.py::test_sse_before_and_after_headers tests/backend/test_a9.py::test_live_http_stream_releases_on_completion_disconnect_or_revocation --durations=5
```

**29 casos distintos aprovados em 135,95 s**, log tmp/i3-directed.log: 19 próprios e dez regressões próximas.
Os próprios cobrem 13 cenários do proxy, cinco valores inválidos do timeout de modelo e contrato estático do Nginx.
Os próximos verificam limite real ASGI, erros SSE antes/depois dos cabeçalhos e liberação de stream HTTP por término, desconexão e revogação.

A rota TypeScript real foi compilada em memória com o TypeScript instalado e executada com NextRequest e streams nativos do Node.
Parte das sondas usa servidor HTTP local real; falhas e retornos específicos usam doubles controlados.
Não é teste de uma aplicação Next implantada nem da cadeia Nginx/Compose.
A primeira seleção teve 27 aprovados e uma falha na entrega SSE sob prazo sintético de inatividade de um segundo.
A prova de entrega passou a usar prazo de dez segundos; a prova específica de inatividade mantém prazo curto e falha controlada.
Foram acrescentadas a proteção de leitura lenta e a coordenação de cancelamento antes da seleção final.
Não somar repetições aos 29 casos distintos. Durações variáveis não isolam causa de desempenho.

Aceite funcional dirigido I3 comprovado localmente. Lint e tipagem do portal e suíte completa serão registrados no fechamento I.
Docker Linux e executável Nginx indisponíveis: configuração Nginx verificada estaticamente, sem afirmar homologação real.
PostgreSQL, Hermes/LangGraph e LLM reais continuam pendentes do bloco H e das equipes responsáveis.
Sem atualização de dependências, migração de base operacional, commit, push, PR ou deploy nesta etapa.


## Verificação final do consumidor

Lint Next da rota e TypeScript do portal (`tsc --noEmit --incremental false`) terminaram com código 0, sem avisos ESLint.
Log: tmp/i3-portal-check.log; a ausência de saída do tsc acompanha o encerramento bem-sucedido do comando.
Após estabilizar a sonda de entrega SSE por handshake, os 19 casos próprios passaram novamente em 8,67 s, sem skips, tmp/i3-final-own.log.
O upstream envia o evento terminal somente após o cliente ler o primeiro chunk; isso comprova entrega incremental sem depender de uma espera fixa de 500 ms.
A sonda específica de inatividade continua exercitando seu timeout de 50 ms; cenários de cancelamento usam prazo separado de dez segundos.
O processo Node tem limite externo de 60 s para falhar de forma delimitada em ambientes lentos.

Portabilidade da suíte Python: as 13 sondas da rota têm skip explícito quando Node ou Next/TypeScript locais não estão instalados.
Os demais casos I3 não dependem desses pacotes. A CI Python atual não instala o portal; esse skip não comprova o proxy naquele ambiente.
Para executar as sondas, instalar as dependências do portal com npm ci e rodar a seleção I3.
Nesta worktree todos os 19 casos foram efetivamente executados. Não houve instalação, download ou atualização de dependências nesta rodada.

# A0 — Comportamento HTTP compartilhado

Data: 30/10/2026. Escopo: A0 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree oficial `backend-tools`, branch `team/backend`. O pedido “Faça A0” autoriza esta etapa local.
Não presume revisão CTO/Astra concluída nem aceite global do bloco F.

## Causa e implementação

Erros do framework tinham envelope diferente. Falhas inesperadas e validação de saída não tinham tratamento compartilhado seguro.
Faltavam challenge Bearer, política comum de cache e limite de corpo no servidor.

- `HTTPBoundary` recebe no máximo 1.048.576 bytes antes de entregar a entrada ao endpoint.
- Conta bytes efetivos mesmo sem Content-Length, em partes ou com tamanho declarado menor.
- Content-Length acima do limite recusa antes da leitura; valores numéricos extensos não exigem conversão inteira.
- Não lê partes adicionais após detectar excesso. Não armazena o corpo recusado na auditoria.
- Respostas privadas recebem `Cache-Control: no-store`, incluindo recusas e erros. Saúde/docs públicos mantêm comportamento próprio quando não há Authorization.
- 401 recebe `WWW-Authenticate: Bearer` quando não há challenge explícito; demais cabeçalhos do framework são preservados.
- HTTPException conserva status e cabeçalhos, incluindo Allow em 405; seu detail não é exposto.
- ResponseValidationError retorna 500 invalid_response, sem dados rejeitados.
- Exceção inesperada anterior à resposta retorna 500 internal_error, sem detalhes ou traceback nos logs da aplicação.
- Falha do banco continua 503 storage_unavailable; erro de entrada continua 422 validation_error.
- Cancelamento e desconexão não são convertidos indiscriminadamente em erro de validação.

A fronteira não bufferiza a saída SSE. Falha de autorização, leitura ou serialização após abertura chega como um único stream_error e encerra o fluxo.
Depois de enviados os cabeçalhos, não tenta emitir outra resposta HTTP. Serialização dos eventos também fica protegida.

## Catálogo de respostas

| Situação | HTTP | code | Cabeçalho / observação |
| --- | --- | --- | --- |
| Credencial ausente/inválida | 401 | unauthorized | Challenge Bearer |
| Permissão recusada | 403 | forbidden | Mantém regra do domínio |
| Recurso ausente | 404 | not_found | Envelope comum |
| Método incompatível | 405 | method_not_allowed | Allow preservado |
| Corpo acima de 1 MiB | 413 | payload_too_large | Não executa domínio |
| Entrada inválida | 422 | validation_error | Não ecoa conteúdo |
| Saída fora do contrato HTTP | 500 | invalid_response | Não ecoa dados rejeitados |
| Exceção inesperada | 500 | internal_error | Mensagem genérica |
| Banco indisponível | 503 | storage_unavailable | retryable preservado |
| Outro erro explícito do framework | status original | http_error | Sem detail |
| Erro após abertura do SSE | 200 já enviado | code no stream_error | Encerra conexão; não muda status |

Erros de negócio existentes, incluindo conflitos, conservam seus códigos/status.
ErrorCode acrescenta internal_error, http_error, method_not_allowed e payload_too_large.
ToolError mantém campos e tipagem estrita. OpenAPI passa a documentar os erros HTTP compartilhados e os cabeçalhos pertinentes.
O cliente comum síncrono/assíncrono já consome ToolError; códigos novos não introduzem retry automático.

## Workflow e rastreamento

1. Middleware F0 registra UUID físico para rota de ferramenta conhecida.
2. A0 limita e recompõe o corpo; excesso termina com 413 antes de autenticação e domínio.
3. Framework valida a entrada; autenticação e serviço preservam suas regras atuais.
4. Endpoint produz saída validada pelo response_model.
5. A0 aplica envelope seguro e cabeçalhos. F0 registra status/código preparados na mesma tentativa.
6. SSE valida acesso antes da abertura e revalida durante leitura; erros posteriores usam stream_error.

413 de tool produz tentativa física sem vínculo lógico/run. Não usa entrada parcial para atribuir orçamento ou identidade.
Falha interna tratada agora prepara 500: F0 registra failed/prepared/internal_error e client_received null.
O teste histórico de RuntimeError foi atualizado para esse comportamento público novo; não se removeu a conferência no banco.
Efeito confirmado, replay, orçamento e fontes permanecem regidos pelo bloco F.
Resposta preparada não comprova recebimento ou leitura pelo cliente.

## Evidências

Novo [test_a0.py](../../tests/backend/test_a0.py): 12 casos, incluindo mensagens ASGI efetivamente fragmentadas.
Confere fronteira exata de 1 MiB, excesso acumulado, ausência/tamanho falso de Content-Length e tamanho declarado extenso.
Confere 404/405/401, Allow/challenge, no-store, distinção entre entrada/saída/erro interno, logs sem marcador privado e 413 registrado no banco.
SSE cobre falhas de banco, domínio e internas antes/depois da abertura; prova também entrega imediata e ausência de segunda resposta.

```sh
uv run --locked python -m pytest tests/backend/test_a0.py tests/backend/test_f0.py tests/backend/test_openapi.py
```

**26 aprovados em SQLite**, 55,50 s. Um aviso de depreciação Starlette/HTTPX.
Ajustes iniciais de lint/formato foram corrigidos antes da verificação ampliada.
A primeira rodada ampliada foi interrompida após encontrar uma expectativa histórica de ResponseValidationError propagado.
O teste de contexto de run malformado agora exige 500 invalid_response, sem contexto exposto e com no-store.
A suíte completa foi reiniciada após essa atualização de contrato.

Verificação ampliada retomada após interrupção da sessão: **283 testes aprovados em SQLite**, 1.548,55 s (25min48s).
Saída preservada em tmp/a0-check.log; código final 0 em tmp/a0-check.exit.
Os 26 testes dirigidos fazem parte dos 283; não somar as contagens.

## Consumidores e limites

Backend, portal/proxy, workers, agentes e revisão técnica devem considerar o novo 413 e os códigos compartilhados.
O limite pertence ao corpo recebido pela aplicação; homologação do transporte HTTP/proxy permanece I3.
A0 não altera regras de propriedade, grants, leases, resultado declarado, quotas de fila ou GET de artefato.
Não há migração, reparo de dados ou chamada aos runtimes reais nesta etapa.

PostgreSQL indisponível: `docker ps` falhou por ausência do pipe dockerDesktopLinuxEngine.
SQLite não homologa concorrência PostgreSQL. Revisão CTO/Astra permanece manual, pelo responsável.
Sincronização/merge com main não executada nesta worktree com alterações locais e autorização restrita a implementação local.
Sem commit, merge, push, PR, publicação, deploy ou revisão automática.
A1 e demais endpoints permanecem separados; não foram iniciados nesta entrega.

## Limitação da sessão retomada

Após a interrupção, o drive D: deixou de estar acessível nesta sessão. O arquivo .git desta worktree aponta para D:/benchmark-ciia-hermes/.git/worktrees/benchmark-ciia-hermes.
Os arquivos de trabalho em C: permanecem acessíveis. Git status/diff finais falham por ausência desses metadados; não houve reparo, recriação ou alteração do histórico.
A conferência git diff --check havia passado antes da interrupção. A validação final de diff Git exige restabelecer o drive D:.

## Arquivos da implementação A0

- [http_boundary.py](../../services/backend/http_boundary.py): limite do corpo, cabeçalhos e falha interna anterior à resposta.
- [app.py](../../services/backend/app.py): montagem da fronteira, handlers de framework/saída, SSE e descrição OpenAPI.
- [models.py](../../contracts/models.py): quatro novos códigos tipados no envelope compartilhado.
- [openapi.yaml](../../services/backend/openapi.yaml): contrato HTTP gerado.
- [test_a0.py](../../tests/backend/test_a0.py): provas específicas da fronteira.
- [test_f0.py](../../tests/backend/test_f0.py) e [test_contract_security.py](../../tests/backend/test_contract_security.py): expectativas históricas adaptadas ao 500 seguro, mantendo as conferências.

Documentação de contratos, referência HTTP, índice operacional e planos também receberam o registro da etapa.

## Resultado final

- `uv run --locked python -m scripts.dev check`: aprovado; 283 testes, 1.548,55 s.
- Lint: aprovado. Formato: 169 arquivos aprovados. Links, YAML e invariantes do repositório aprovados.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado após as alterações executáveis finais.
- `uv run --locked python -m scripts.validate_repository`: aprovado após a documentação.
- `git diff --check`: aprovado antes da interrupção; conferência final indisponível por ausência do drive D: e dos metadados referenciados.

Um aviso existente de depreciação Starlette/HTTPX permanece.
Testes abrangem fronteira HTTP, seis ferramentas, autorização, orçamento, concorrência, migrações, rollback, replay, perda de resposta e clientes.
Estado: A0 implementado e verificado localmente em SQLite. PostgreSQL, revisão manual CTO/Astra e conferência Git final permanecem pendentes.
A1 não foi iniciado. Nenhum aceite global de segurança ou autorização de publicação é inferido desse resultado.

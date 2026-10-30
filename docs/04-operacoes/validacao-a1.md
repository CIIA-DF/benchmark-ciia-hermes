# A1 — GET de artefatos com integridade persistida

Data: 30/10/2026. Escopo: A1 do [plano vigente](../02-arquitetura/backend-plano-blocos.md).
Worktree: `C:/Users/roger/.codex/worktrees/backend-tools/benchmark-ciia-hermes`, branch `team/backend` conferida nesta execução.
Relatório conciso; implementação local. Testes dirigidos conforme solicitação do responsável. Suíte completa reservada ao fechamento do bloco A.

## Falha reproduzida e correção

O GET conferia proprietário e grants, mas devolvia payload/recibo sem validar a consistência persistida.
Alterar apenas o conteúdo de um artefato válido mantinha HTTP 200 nas duas ferramentas de escrita.

Prova anterior à correção: dois testes falharam na expectativa de 500; ambos receberam 200 para conteúdo adulterado.
Comando: `uv run --locked python -m pytest tests/backend/test_a1.py -k rejects_corruption --durations=5`.
Resultado esperado da reprodução: 2 falhas, 4 não selecionados, 83,82 s. A primeira preparação consumiu 30,87 s.

[ExecutionService.get_artifact](../../services/backend/execution.py) agora reutiliza [validate_artifact](../../services/backend/artifact_integrity.py), extraído no F5.
O retorno interno é `ArtifactResponse`, tipado. O formato JSON público permanece igual.
Contexto esperado vem do run autorizado, nunca do payload/recibo a conferir.
Contexto inválido, não canônico ou com run_id diferente da linha do run produz 500 invalid_response seguro.
KeyError/TypeError da leitura de contexto persistido também recebem esse tratamento; falhas SQL continuam no tratamento 503 de A0.

O validador comum confere:

- Ferramenta suportada e modelo de entrada correspondente.
- Payload completo validado e canônico, sem campos incompatíveis com a ferramenta.
- run_id, process_id, corpus_version e requirements_version do payload/recibo contra o contexto confiável.
- UUID do recibo contra o artefato persistido.
- input_sha256 da entrada canônica e content_sha256 do conteúdo UTF-8.
- Chave de idempotência persistida contra o payload.
- Recibo persistido original, com replayed false.

Não houve alteração no escritor, no validador compartilhado, no algoritmo de hash ou nas migrações.
[app.py](../../services/backend/app.py) e [OpenAPI](../../services/backend/openapi.yaml) descrevem a integridade e o 500 explícito do endpoint.

## Workflow e consumidores

1. Tool de escrita confirma artefato/recibo no fluxo F5/F6.
2. Seu artifact_id alimenta `GET /artifacts/{id}`; o operador envia Authorization Bearer.
3. Servidor busca a linha pelo UUID; ausência conserva 404.
4. `owned_run` conserva perfil de operador, propriedade do run e grants atuais de processo/corpus.
5. Contexto persistido do run é validado e comparado à identidade da linha.
6. `validate_artifact` confere ferramenta, payload, recibo, contexto, identificadores e hashes.
7. Retorna ArtifactResponse com 200 ou envelope seguro de erro. GET não repara nem regrava os dados.

Portal, operadores e consumidores HTTP do artefato recebem o mesmo schema. Registros inconsistentes deixam de retornar sucesso.
Leitura de efeito confirmado não exige can_write nem lease ativo. O recibo original continua replayed false após retry da escrita.
Autorização precede integridade do artefato: operador estrangeiro mantém 404 e worker mantém 403, inclusive com recibo corrompido.
Grants revogados continuam 403. Nenhum campo sensível é ecoado na resposta de falha.

| Situação | HTTP | code |
| --- | --- | --- |
| Artefato íntegro e acesso concedido | 200 | ArtifactResponse |
| Credencial ausente/inválida | 401 | unauthorized |
| Worker ou concessão revogada | 403 | forbidden |
| Artefato ausente ou run de outro proprietário | 404 | not_found |
| UUID de rota inválido | 422 | validation_error |
| Corrupção acessível ao proprietário autorizado | 500 | invalid_response |
| Falha SQL | 503 | storage_unavailable |

Respostas privadas preservam no-store e o envelope de A0. Essas garantias conferem consistência; não certificam qualidade semântica ou autenticidade contra alteração coordenada de toda a base.

## Testes próprios e seleção dirigida

Novo [test_a1.py](../../tests/backend/test_a1.py): seis casos pytest, incluindo as duas ferramentas.
Dois casos agrupam 19 alterações isoladas por ferramenta, cada qual com identificação da falha e restauração do registro original.
Isso evita repetir preparação de banco/credenciais para cada campo; não são 38 testes pytest adicionais.

Variações: conteúdo, normalização canônica, quatro campos de contexto no payload e no recibo, UUID, dois hashes, replay persistido, chave, ferramenta oposta/desconhecida e objetos nulos.
Testes confirmam que a recusa não modifica a linha adulterada e que os dados restaurados voltam a retornar o mesmo 200.
Outros casos cobrem autenticação, proprietário estrangeiro com mesmo grant, worker, grant revogado, can_write false, lease expirado, recurso ausente, UUID inválido e 503 seguro.
Contexto do run cobre null, lista, campos ausentes/inválidos, normalização e identidade divergente.
Artefato reassociado a outro run existente do mesmo proprietário também é recusado.

Oito regressões próximas: três do validador F5, jornada F6 sem checklist, duas de escrita/replay/GET e duas do OpenAPI.

```sh
uv run --locked python -m pytest tests/backend/test_a1.py tests/backend/test_f5.py::test_integrity_validator_uses_trusted_run_context_without_write_request tests/backend/test_f6.py::test_search_read_draft_replay_keeps_scope_hash_and_physical_phases_without_checklist tests/backend/test_execution.py::test_writes_are_idempotent_and_independently_readable tests/backend/test_openapi.py --durations=10
```

**14 aprovados em SQLite, 94,72 s (1min35s).** São seis próprios e oito próximos; as duas reproduções anteriores são subconjunto repetido, não testes adicionais aprovados.
Log: `tmp/a1-directed.log`; código final 0 em `tmp/a1-directed.exit`.

Maiores fases observadas: chamada do caso de corrupção da pendência, 21,19 s; chamadas dos casos de escrita/replay/GET, 19,85 s e 14,80 s; preparações desses casos, 13,83 s e 11,65 s.
Durações incluem fixture e chamadas locais; essa amostra não isola causa nem permite comparar desempenho das ferramentas.
Um aviso existente de depreciação Starlette/HTTPX permanece.

## Verificações e limites

Lint e formato dos três arquivos Python alterados aprovados. OpenAPI regenerado.
Diff de implementação comparado à cópia anterior à alteração A1; alterações anteriores preservadas.
`uv run --locked python -m scripts.export_openapi --check`: aprovado.
`uv run --locked python -m scripts.validate_repository`: aprovado.
`git -c core.safecrlf=false diff --check`: aprovado.
Estado: A1 implementado e verificado localmente; disponível para revisão manual.

Suíte completa não executada: fica para o fechamento do bloco A, conforme pedido explícito.
PostgreSQL e runtimes reais não exercitados nesta etapa local em SQLite; homologação PostgreSQL continua no bloco H.
GET usa integridade estrutural e contexto persistido, sem reexecutar a regra de criação nem homologar fontes ou qualidade metodológica.
Sem merge de main nesta worktree com alterações locais e autorização restrita à entrega local.
Sem commit, push, PR, publicação, deploy ou revisão automática CTO/Astra. A2 não iniciado.

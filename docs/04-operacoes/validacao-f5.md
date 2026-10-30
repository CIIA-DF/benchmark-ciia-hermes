# F5 — registrar_pendencia

F5 do [plano vigente](../02-arquitetura/backend-plano-blocos.md). Worktree oficial team/backend. Relatório conciso conforme preferência do responsável.

## Entrega

Validação de integridade extraída para services/backend/artifact_integrity.py. Função validate_artifact recebe registro, ferramenta esperada e ToolContext confiável. Retorna ArtifactResponse tipado.

A função não depende de requisição, lease, conexão SQL ou ExecutionService. Autorizações e concessões continuam responsabilidade do chamador.

ExecutionService.artifact_receipt preserva sua assinatura. Delega a integridade estrutural e mantém a comparação com a entrada exata quando same_input=true.

Hash canônico movido para services/backend/hashing.py, sem alterar algoritmo. execution.digest permanece importável, preservando consumidores existentes.

GET /artifacts/{id} não foi alterado. A1 poderá reutilizar a função após autorizar o proprietário e obter contexto confiável do run.

Sem nova rota, modelo público, dependência ou migração. A extração afeta o escritor comum das duas ferramentas; aceite específico F6 permanece separado.

## Integridade e contratos

Conferências preservadas:

- ferramenta permitida e coerente com o registro;
- run, contexto de payload/recibo e chave de idempotência;
- payload validado pelo modelo específico da ferramenta e representação canônica preservada;
- input_sha256 da entrada completa;
- artifact_id do recibo igual à chave persistida;
- content_sha256 do conteúdo UTF-8 validado;
- UUID, timestamp com fuso e replayed=false no recibo persistido.

Na nova escrita/releitura, a fachada exige payload idêntico ao pedido. No replay, distingue registro íntegro com outra entrada (409) de corrupção (500).

A função retorna 500 invalid_response seguro para inconsistência. Não verifica propriedade, concessões, sustentação semântica ou autenticidade criptográfica independente do armazenamento.

PendencyInput e WriteReceipt permanecem iguais. Backend, Documentos, agentes e Metodologia devem revisar a fronteira antes da integração compartilhada.

## Workflow e fases

1. Checklist fornece requirement_id versionado. Busca/inventário fornece evidências autorizadas.
2. Cliente injeta contexto, credenciais, lease e ID lógico.
3. F0 registra UUID físico; reserva lógica durável precede domínio.
4. Transação revalida permissões atuais, requisito e evidências.
5. Escritor valida registro/recibo, persiste e relê antes do commit.
6. Artefato, recibo e effect_confirmed confirmam juntos.
7. Releitura independente confirma o retorno; conclusão usa o mesmo UUID físico.
8. Cliente confere contexto/hash. Operador pode conferir conteúdo e recibo pelo GET vigente.

Falha antes do commit desfaz artefato e fase de efeito; started e failed sobrevivem.

Falha de confirmação após commit preserva efeito. Retry mantém ID lógico/corpo/chave e abre outra tentativa física.

Aceite F0/F5: duas requisições após falha pós-commit e retry; um artefato. Fases não duplicam tentativa física.

client_received permanece null. Ledger antigo representa estágios; contagens físicas usam ToolTracking.history.

## Evidências

Skill safe-refactor aplicada. Prova idêntica executada antes e depois da extração:

```sh
uv run --locked python -m pytest tests/backend/test_t5.py::test_checklist_search_to_confirmed_pendency_with_independent_hash tests/backend/test_f0.py::test_postcommit_retry_is_two_physical_attempts_and_one_artifact
```

Três aprovados antes; três aprovados depois. Essa prova integra as regressões seguintes; não somar como cobertura adicional.

Novo [test_f5.py](../../tests/backend/test_f5.py): cinco casos.

- Concorrência na pendência: dois UUIDs físicos, um artefato, uma escrita e um replay.
- Rollback após registrar efeito: nenhuma confirmação falsa sobrevive. Mesma identidade recupera operação, com uma reserva lógica.
- Três casos do validador reutilizável: contexto confiável divergente, ferramenta incompatível e UUID de recibo adulterado.

Os três últimos usam registro produzido via HTTP. Comparam o resultado tipado com GET válido e verificam ausência de mutação.

Regressões T5 cobrem requisito, evidências, corrupção, hashes, rollback e recuperação. F0 cobre falha pós-commit, tentativas e fases.

T0-R1 verifica revogação atual de worker/proprietário. Protocolo dos adaptadores verifica consumo comum.

Comando dirigido:

```sh
uv run --locked python -m pytest tests/backend/test_f5.py tests/backend/test_t5.py tests/backend/test_f0.py tests/backend/test_t0_r1.py tests/integration/test_adapter_protocol.py
```

**57 aprovados em SQLite**, 272,07 s. Inclui cinco cenários novos e 52 regressões pertinentes.

## Limitações

PostgreSQL não executado: Docker Linux indisponível; pipe dockerDesktopLinuxEngine ausente. SQLite não homologa travas, concorrência ou recuperação PostgreSQL.

Refatoração verificada antes/depois e por regressões dirigidas. Suíte completa permanece prevista no fechamento principal F.

Última suíte completa histórica: F0, 231 aprovados. Não é resultado novo F5.

GET mantém implementação anterior. Seu aceite de integridade e erro uniforme pertence a A1/A0; não foi antecipado.

Fixtures e bancos sintéticos temporários. Nenhum corpus real, banco operacional ou migração foi alterado nesta rodada.

Histórico e alterações anteriores preservados. Sem commit, merge, push, PR, publicação ou revisão automática/Astra.

Estado: F5 implementado e verificado localmente. PostgreSQL e aceite manual pendentes. F6 aguarda liberação.


## Verificações finais

- Prova de preservação: três aprovados antes, três depois da extração.
- Testes dirigidos finais: 57 aprovados, 272,07 s. A prova anterior é subconjunto dessa cobertura.
- `uv run --locked python -m ruff check .`: aprovado.
- `uv run --locked python -m ruff format --check .`: aprovado.
- `uv run --locked python -m scripts.validate_repository`: aprovado.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado.
- `git diff --check`: aprovado.

Um aviso de depreciação Starlette/HTTPX permanece. Suíte completa não repetida nesta rodada dirigida; fechamento principal F mantém essa exigência.

F5 encerrado como implementação/verificação local. PostgreSQL, revisão manual e integração do GET permanecem pendentes nos blocos próprios.

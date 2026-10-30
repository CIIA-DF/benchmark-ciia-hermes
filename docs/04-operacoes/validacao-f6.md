# F6 — salvar_minuta e fechamento local do bloco F

Escopo: F6 e fechamento F do [plano vigente](../02-arquitetura/backend-plano-blocos.md). Worktree oficial team/backend. Relatório conciso conforme preferência do responsável.

## Entrega

Integração T6/F0/F5 preservada. Nenhuma falha funcional nova foi reproduzida. Entrega acrescenta dois testes integrados e matriz de fechamento.

Código de produção, contratos, OpenAPI e migrações permanecem iguais nesta rodada. A extração F5 é exercitada também pela minuta.

## Workflow e dados

1. Busca retorna document_id/chunk_id/page no processo/corpus autorizado.
2. Leitura retorna texto e origem das páginas pedidas.
3. Cliente injeta contexto e cabeçalhos técnicos no WriteInput.
4. F0 registra UUID físico e reserva lógica antes do domínio.
5. Escritor revalida permissões atuais, fontes, payload, hashes e recibo.
6. Artefato, recibo e effect_confirmed confirmam na mesma transação.
7. Releitura independente confirma retorno; cliente confere contexto e hash.
8. Operador pode conferir conteúdo e recibo pelo GET vigente.

Minuta não exige checklist cadastrado, requirement_id ou pendência prévia. requirements_version continua parte do contexto do run.

Hash do recibo corresponde ao conteúdo validado em UTF-8. input_sha256 corresponde à entrada canônica completa.

Existência de fonte não comprova sustentação semântica. Recibo não certifica qualidade científica ou recebimento pelo cliente.

## Aceite F6

Novo [test_f6.py](../../tests/backend/test_f6.py), dois cenários:

- Busca, leitura, minuta e retry sem checklist: um artefato; três reservas lógicas e quatro tentativas físicas.
- Concorrência da minuta: uma reserva lógica; dois UUIDs físicos; uma escrita e um replay do mesmo artefato.

Conferências diretas: payload normalizado, hash, contexto confiável no validate_artifact e igualdade com GET de dados válidos.

Fases da escrita: started, effect_confirmed, completed. Replay confirma efeito existente; não cria outro artefato. client_received permanece null.

Regressões T6 verificam recibos adulterados nos clientes síncrono/assíncrono, conteúdo, fontes, orçamento, concorrência, rollback e recuperação.

F0 verifica falha de confirmação pós-commit: duas tentativas físicas e um artefato. T0-R1/R2 preservam autorização atual e reserva anterior ao domínio.

Execução inicial:

```sh
uv run --locked python -m pytest tests/backend/test_f6.py
```

**2 aprovados em SQLite**, 18,39 s. Um aviso de depreciação Starlette/HTTPX permanece.

## Matriz individual do bloco F

| Bloco | Implementação | Prova local registrada | Pendência |
| --- | --- | --- | --- |
| F0 | Migração 0006; tentativas físicas e fases | [F0](validacao-f0.md): rastreamento, migração, rollback, transporte | PostgreSQL; aceite manual |
| F1 | Consulta preservada com F0 | [F1](validacao-f1.md): processo, inventário, erros e reservas | PostgreSQL; aceite manual |
| F2 | Rejeição explícita de U+0000 no contrato | [F2](validacao-f2.md): recusa antes do SQL, orçamento, Unicode, isolamento | PostgreSQL/locale; aceite manual |
| F3 | Leitura T3 preservada com F0 | [F3](validacao-f3.md): páginas exatas, lacunas, hash integral e erros | PostgreSQL; aceite manual |
| F4 | Checklist T4 preservado com F0 | [F4](validacao-f4.md): identidade, versão, unicidade e pendência | PostgreSQL; Metodologia; aceite manual |
| F5 | Integridade extraída; fachada preservada | [F5](validacao-f5.md): contexto confiável, permissões, rollback e replay | PostgreSQL; adoção futura pelo GET; aceite manual |
| F6 | Minuta preservada após F5 | Este registro: jornada, concorrência e suíte de fechamento | PostgreSQL; aceite manual |

A suíte de fechamento revalida os registros históricos; não soma suas contagens como testes distintos adicionais.

## Verificações de fechamento

Comando obrigatório:

```sh
uv run --locked python -m scripts.dev check
```

**271 aprovados em SQLite**, 893,63 s. Lint, formato e links/invariantes também aprovados.

Reservas, tentativas, fases e artefatos são conferidos diretamente nos bancos sintéticos pelos testes F0–F6.

## Limitações e liberação

PostgreSQL não executado: Docker Linux indisponível; pipe dockerDesktopLinuxEngine ausente. SQLite não homologa travas, concorrência, migração ou restauração PostgreSQL.

Runtimes reais, conteúdo metodológico e revisão CTO/Astra permanecem pendentes. Implementação, verificação local e liberação manual continuam estados distintos.

Nenhuma migração foi aplicada a banco operacional. GET de artefatos mantém implementação anterior; seu aceite completo pertence a A1/A0.

Histórico e alterações anteriores preservados. Sem commit, merge, push, PR, publicação ou revisão automática.

Estado: F6 preservado e verificado. Bloco F0–F6 verificado localmente pela suíte completa de 271 testes. Revisão manual e PostgreSQL pendentes.

APIs não iniciadas. A0 depende de liberação explícita após revisão do bloco F. Aprovação não autoriza deploy.


## Resultado final

- `uv run --locked python -m scripts.dev check`: 271 testes aprovados, 893,63 s; lint, formato e validação do repositório aprovados.
- Os dois testes novos passaram também na execução inicial, 18,39 s. São parte dos 271; não somar novamente.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado.
- `uv run --locked python -m scripts.validate_repository`: aprovado após documentação.
- `git diff --check`: aprovado.

A suíte inclui as seis ferramentas, migrações, autorização, orçamento, concorrência, rollback, replay e perda de resposta.

Fases, reservas e artefatos foram conferidos nos bancos sintéticos pelos testes. Um aviso de depreciação Starlette/HTTPX permanece.

Matriz F0–F6: implementação e verificação local concluídas. Homologação PostgreSQL, revisão CTO/Astra e liberação do responsável continuam pendentes.

Bloco F disponível para revisão manual. A0 só começa após liberação explícita; nenhuma aprovação implica autorização de deploy.

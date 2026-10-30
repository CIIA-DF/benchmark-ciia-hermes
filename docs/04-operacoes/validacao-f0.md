# F0 — base compartilhada de rastreamento

Escopo liberado: F0 do [plano fornecido pelo responsável](../02-arquitetura/backend-plano-blocos.md). Worktree oficial team/backend. Alterações anteriores, inclusive observabilidade/output/tmp presentes no início desta rodada, preservadas. Sem commit, merge, push, PR, deploy ou revisão automática/Astra. F1 e APIs aguardam liberação.

## Causa e implementação

O histórico anterior tinha três linhas 200/503/200 para duas requisições no cenário commit → falha de confirmação → retry. Essas linhas continuam válidas como estágios de compatibilidade, mas não definem a contagem física. Não há evidência para reconstruir a cardinalidade física de registros antigos.

[ADR 008](../05-decisoes/008-tentativas-fisicas-tools.md) acrescenta a definição de tentativa física. A migração 0006, após 0005, cria duas tabelas independentes, sem modificar registros nem migrações anteriores:

- physical_tool_attempts: UUID gerado pelo servidor, ferramenta/método, início/fim, associação autorizada a run/ID lógico/hash, estado da resposta preparada, HTTP/código observados e client_received nullable.
- physical_tool_phases: UUID físico + fase como chave; instante, artefato e replay quando aplicáveis. Fases ordenadas semanticamente, inclusive com timestamps iguais.

ToolTracking implementa início durável, associação na reserva, fase de efeito na transação do artefato, conclusão independente e leitura tipada. PhysicalToolAttempt/PhysicalToolPhase são modelos internos compartilhados; não introduzem endpoints. O middleware das seis rotas propaga o mesmo UUID a chamadas válidas e validação recusada. Uma credencial inválida não permite atribuir o run alegado no corpo; a tentativa sem atribuição ainda pode registrar o HTTP preparado.

## Workflow e fronteiras de confirmação

Requisição da tool → UUID físico e started duráveis → autenticação/validação → contexto/reserva atribuível → identidade lógica durável antes do domínio → transação de leitura/efeito com autorização atual → artefato/recibo e effect_confirmed atômicos → releitura independente → resposta preparada completed/failed na mesma tentativa física.

Se o efeito falhar antes do commit, sua fase desaparece no rollback; fase started e auditoria de falha sobrevivem. Se só a releitura falhar, o efeito permanece e a mesma tentativa termina failed com HTTP 503 preparado. Retry abre outro UUID físico, mantém o ID lógico/corpo/chave e confirma replay do mesmo artefato. effect_confirmed com replayed=true confirma efeito existente, não um segundo artefato.

Leituras não criam fase de artefato: started → completed/failed. Uma exceção não tratada antes de observar resposta resulta interrupted/http_status=null; não se infere o que middleware externo eventualmente enviou. Toda conclusão preparada mantém client_received=null; ausência de informação não é false, true ou sucesso metodológico.

## Contratos, consumidores e compatibilidade

| Elemento | Tratamento F0 |
| --- | --- |
| logical_tool_calls | Identidade/orçamento lógico preservados, reserva antes do domínio |
| physical_tool_attempts | Uma linha por requisição de rota conhecida observada, inclusive erros sem atribuição |
| physical_tool_phases | Estágios ligados ao mesmo UUID; efeito usa a conexão da transação do artefato |
| tool_calls/tool_call_history | Ledger de compatibilidade; linhas não equivalem a tentativas físicas |
| ToolTracking.history | Fonte canônica tipada para novas contagens físicas por run |
| Eventos SSE/clientes | Protocolo legado preservado; adoção ampla de correlação fica em I1/A/E |
| API/OpenAPI | Rotas, códigos, modelos de resposta e cabeçalhos públicos preservados |

Nenhum backfill físico foi realizado. Não unir registros antigos em tentativas presumidas nem somar ledger de estágios com a fonte canônica como requisições distintas. A leitura por run exclui tentativas sem atribuição; a tabela física preserva essas lacunas para investigação administrativa futura. Campos de vínculo nulos não autorizam inferir execução inexistente.

O código de erro da resposta é registrado quando o handler o conhece. Erros do framework sem essa informação mantêm code=null, mesmo quando há HTTP conhecido. Chamadas internas ao serviço não representam requisições HTTP: sem UUID recebido da fronteira, não se inventa uma tentativa física. Corpo/argumentos/credenciais nunca são gravados em claro.

O novo plano foi preservado em backend-plano-blocos.md; o plano T0–T6 permanece como histórico e aponta para a nova ordem. F0 não executa F2 (NUL), A0, A1, A2, quotas, exportação ou observabilidade formal. Backend, agentes e Metodologia devem revisar o contrato de rastreamento antes de integração compartilhada.

## Cenários e resultados

Novo [test_f0.py](../../tests/backend/test_f0.py), 12 cenários HTTP/banco:

- Falha de releitura pós-commit e retry para cada escrita: duas tentativas físicas distintas, um artefato, fases e replay corretos, recebimento desconhecido.
- Rollback depois de inserir fase de efeito: nenhuma fase de efeito confirmada sobrevive; retry mantém identidade lógica e recupera operação.
- Validação recusada e reutilização inválida: uma tentativa física para cada requisição, com resposta e hash próprios.
- Credencial inválida: 401 observado sem associar o run informado por corpo não confiável.
- Concorrência: dois UUIDs físicos e um único efeito, sem colapsar requisições que compartilham ID lógico.
- Leitura: fases started/completed, sem inventar confirmação de artefato ou recebimento pelo cliente.
- Migração 0005 → 0006: ledger antigo idêntico, fonte física vazia até nova requisição; downgrade/upgrade somente em banco sintético.
- Relógio fixo: ordem started/effect_confirmed/completed independe da resolução de timestamp.
- Coleta final indisponível: efeito permanece, status/fim continuam desconhecidos e log seguro contém UUID de correlação.
- Interrupção sem resposta observada: estado interrupted, HTTP null, sem inventar resposta preparada.
- Perda de resposta no transporte: retry gera dois UUIDs físicos com um ID lógico e um artefato; ambos os recebimentos continuam desconhecidos.

Primeira execução dirigida (F0/T0/T0-R1/T0-R2/tool_calls/migrações): 47 aprovados e 1 falha por ordenação alfabética de fases com mesmo timestamp no Windows. A causa foi corrigida usando ordem semântica, sem remover verificação. Após correção, 9 cenários passaram; os três cenários finais de coleta/interrupção/transporte foram acrescentados e a execução final de `uv run --locked python -m pytest tests/backend/test_f0.py` teve **12 aprovados em 23,41 s**, um aviso de depreciação Starlette/HTTPX.

A suíte completa revalidou as regressões iniciais após a correção; resultados finais abaixo.

## Migração, recuperação e limites

0006 é aditiva e foi aplicada somente nos bancos sintéticos dos testes nesta rodada. Não foi aplicada a uma base operacional. Atualizar uma base existente exige backup, migração administrativa revisada e validação da cadeia completa. Downgrade elimina o histórico físico novo; preservar dados exige restauração/reversão em banco separado. O teste de round-trip não substitui homologação de backup/restauração.

Falha de coleta no início produz 503 e log seguro, pois não há como prometer registro durável com banco indisponível. Falha na conclusão preserva início/efeito e expõe lacuna por campos nulos e aviso correlacionado, sem mascarar o efeito confirmado. Crash pode deixar tentativa started; não há reconciliação automática nem inferência de resposta recebida. Timestamps são relógio de parede; ordem semântica das fases não mede latência nem determina ordem causal entre requisições com tempos iguais.

PostgreSQL segue pendente: Docker Linux indisponível na máquina. SQLite não comprova concorrência, travas/FKs, migração ou recuperação em PostgreSQL. Runtimes reais e revisão CTO/Astra permanecem externos/manuais. Retenção, quotas de tentativas e exportação são dos blocos posteriores; F0 não altera orçamento científico.

Estado: F0 implementado e verificado localmente em SQLite. F1 e APIs não iniciados.


## Fechamento das verificações

- `uv run --locked python -m scripts.dev check`: Ruff, formato, links/invariantes e **231 testes aprovados** em SQLite, 927,31 s. Inclui as 219 regressões anteriores e os 12 cenários novos F0.
- `uv run --locked python -m pytest tests/backend/test_f0.py`: **12 aprovados**, 23,41 s. São parte da suíte completa; não somar como cobertura adicional.
- `uv run --locked python -m scripts.export_openapi --check`: aprovado; sem mudança de schema público no F0.
- `uv run --locked python -m scripts.validate_repository`: aprovado após documentação. `git diff --check`: sem erros de whitespace. Base compartilhada, migração e compatibilidade revisadas; trabalho anterior preservado.
- Um aviso de depreciação Starlette/HTTPX permanece. PostgreSQL e restauração operacional não executados: Docker Linux indisponível. Sem aplicação em banco operacional, publicação ou revisão automática.

Matriz de aceite F0: identidade lógica preservada; identidade física distinta por requisição observada; efeito e fases relacionados atomicamente; rollback sem efeito confirmado falso; pós-commit/retry com duas tentativas e um artefato; perda de transporte sem alegação de recebimento; migração sem backfill legado. Verificação local concluída. PostgreSQL, revisão manual e aplicação operacional permanecem pendentes; F1 aguarda solicitação específica.

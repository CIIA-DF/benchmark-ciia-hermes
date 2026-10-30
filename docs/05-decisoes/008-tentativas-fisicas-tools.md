# ADR 008 — tentativas físicas e fases das ferramentas

Estado: implementado localmente no F0; revisão manual e homologação PostgreSQL pendentes. Complementa o ADR 007 sem reescrever seu histórico.

## Problema e decisão

O ledger tool_calls registrava estágios: uma requisição com commit confirmado e falha na releitura podia produzir duas linhas. Não é possível inferir retrospectivamente quantas requisições físicas ocorreram no legado.

A migração aditiva 0006 acrescenta physical_tool_attempts e physical_tool_phases. Um UUID de tentativa nasce no recebimento HTTP de uma rota de ferramenta reconhecida, antes da autenticação/validação. Associação a run/ID lógico/hash só ocorre pelo caminho da reserva autenticada; credenciais, corpos e argumentos em claro não entram no rastreamento. Requisições não atribuíveis ficam sem run.

A identidade lógica e seu orçamento continuam em logical_tool_calls (run_id, tool_call_id), imutavelmente vinculados a ferramenta/hash. O UUID físico nunca é fornecido pelo cliente e não substitui essa identidade.

Fases: started; effect_confirmed, quando há artefato novo ou replay confirmado; completed/failed para resposta preparada, ou interrupted quando não se observou resposta preparada. Confirmação do efeito e sua fase são atômicas na transação do artefato. A conclusão usa transação independente e o mesmo UUID. Ordem das fases é semântica, independente de empate ou recuo do relógio de parede.

http_status representa resposta preparada pelo servidor, não recebimento pelo cliente. client_received permanece null. Na perda da coleta final, started/efeito permanecem e status/fim desconhecidos continuam null; há aviso correlacionado sem conteúdo sensível. Se o banco impedir até o início, responder 503 e registrar falha de coleta em log; não inventar tentativa durável.

## Compatibilidade e consequências

O ledger tool_calls e tool_call_history permanecem como representação de compatibilidade de estágios. Seus registros não são contagem física; novos consumidores devem usar ToolTracking.history e os modelos PhysicalToolAttempt/PhysicalToolPhase. As tabelas novas não recebem backfill. Não somar projeção antiga e tentativas físicas como se fossem requisições adicionais. SSE e clientes legados mantêm o protocolo anterior; adoção ampla, indicadores e exportação são dos blocos próprios.

Não há nova rota, cabeçalho público, DTO de ferramenta ou código HTTP. O OpenAPI permanece coerente sem mudança. Downgrade remove somente as tabelas novas e perde seu histórico: exige backup e execução administrativa isolada, não é reversão preservadora de auditoria.

Aceite F0: falha de confirmação pós-commit e retry = duas tentativas físicas, um artifact_id, fases e HTTP preparados relacionados corretamente. Revisão pelas equipes Backend, agentes e Metodologia antes da integração compartilhada. [Evidências F0](../04-operacoes/validacao-f0.md).

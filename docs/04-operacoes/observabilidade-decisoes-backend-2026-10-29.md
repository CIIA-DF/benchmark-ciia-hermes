# Observabilidade orientada a decisões — Backend & Tools

Data: 29/10/2026. Estado: proposta para revisão; nenhuma implementação autorizada por este documento.

## Objetivo e evidência

Transformar registros de execução em decisões reproduzíveis sobre confiabilidade, recuperação, desempenho e comparação Hermes/LangGraph. Inspeção estática de schema.py, execution.py, app.py, agents/interface.py, scripts/export_chat.py, TDD, contratos e evaluation/protocol.md. Não houve coleta de dados operacionais, execução de testes ou medição de ganhos nesta análise.

As cinco imagens fornecidas pelo responsável orientam a auditoria: parametrização e validação; execução e timeout/retry; ferramenta única; paralelismo; cadeias e grafos com decisões. São referências conceituais, sem impor biblioteca, versão ou sequência obrigatória ao agente.

## Base existente e lacunas

- logical_tool_calls vincula run/ID/ferramenta/hash; tool_calls separa tentativas, início, duração, HTTP, código, replay e artefato. Runs têm início/fim/criação, contexto, executor e resultado. Artefatos permitem conferência independente.
- export_chat lê eventos tool, não o histórico completo tool_calls. Exporta apenas chat e seleciona tool/status/duração/artefato; perde ID lógico, número da tentativa, código HTTP/domínio, replay e hash. Eventos de acompanhamento não devem ser a fonte única de análise. Integrar com A9.
- Duração do cliente e do servidor medem fronteiras diferentes. Não somar nem comparar como se fossem equivalentes. Instrumentação pós-commit precisa distinguir efeito confirmado, releitura do recibo e entrega HTTP. Conferir também a limitação registrada em T5.
- Não existe, nos campos inspecionados, vínculo causal explícito entre resultado de uma tool e entrada de outra. Ordem temporal não demonstra dependência.
- Logs de erro pontuais não substituem rastreamento de todas as rotas, fila, reconexões e experiência do operador. Requests recusados antes de identificar um run precisam de correlação própria, sem atribuição inventada.

## Perguntas, métricas e decisões

| Pergunta | Informação e definição | Decisão suportada |
| --- | --- | --- |
| Os argumentos são adequados? | Primeiras tentativas com validation_error / primeiras tentativas atribuíveis; separar versão, tool e executor | Melhorar schema, descrição e adaptação de argumentos; não atribuir automaticamente a causa ao modelo |
| Retry ajuda? | Chamadas com erro transitório que terminam em sucesso / chamadas com erro transitório; tentativas adicionais por chamada | Ajustar retry, backoff e timeout sem duplicar efeitos |
| Onde está a demora? | Fila = início menos criação; execução = fim menos início; latência HTTP e tempo até primeiro delta medidos separadamente; p50/p95 e tamanho da amostra | Corrigir worker, contenção, transporte ou consulta conforme a fase responsável |
| A busca é útil? | Resultados vazios / buscas concluídas, segmentados por corpus/cobertura; referências retornadas que chegam a leituras e avaliação | Investigar corpus, busca e formulação da consulta com Documentos e agentes |
| Escritas são confiáveis? | Operações com artefato e hash conferidos / operações de escrita elegíveis; separar replay, recusa, resultado desconhecido e duplicação | Corrigir persistência e recuperação; 200 não comprova qualidade semântica |
| Um caminho é eficiente? | Chamadas lógicas por tarefa, loops candidatos, profundidade causal, duração do caminho crítico quando instrumentado | Simplificar chamadas redundantes ou testar paralelismo com dependências demonstradas |
| Qual executor oferece melhor resultado? | Sucesso verificado, latência e custo por tarefa pareada, com versões e orçamento iguais | Escolher configuração sustentada por evidência, com Metodologia |

Ausente não equivale a zero. Percentuais exigem denominador e cobertura. Runs abertos e timeouts permanecem no relatório; não calcular latência apenas dos sucessos sem explicitar o viés. Custo por sucesso é indefinido quando não há sucessos. Não somar durações concorrentes como latência total. Hash igual sugere repetição, mas retry/replay legítimo não é desperdício.

## Roteiro obrigatório das auditorias

1. Fixar objetivo, escopo, estado do código e condições do experimento. Separar observado, declarado, inferido e verificado independentemente.
2. Parametrização: schema estrito, contexto injetado, versões, origem dos argumentos e erros seguros. Propor categorias de erro sem registrar valores rejeitados.
3. Execução: autorização atual, reserva durável, orçamento, timeout, retry, rollback, resposta perdida após commit e auditoria indisponível. Estado desconhecido deve permanecer explícito.
4. Ferramenta única: medir escolha, validação, execução e retorno; não exigir cadeia quando uma chamada basta.
5. Paralelismo: comprovar independência de dados e efeitos, limites de concorrência e contenção. Travas por run podem serializar trabalho mesmo com chamadas HTTP simultâneas. Medir ganho real antes de recomendar mudança.
6. Cadeias: rastrear campos produzidos/consumidos, falha intermediária, repetição, recuperação e qualidade. Busca produz referências; leitura não fabrica chunk_id; requisito alimenta pendência; recibo alimenta conferência de artefato.
7. Grafos: registrar node_id, parent/dependency IDs e categorias de transição quando os adaptadores oferecerem essas informações. Medir loops, fan-out e término. Telemetria declarada do grafo não prova execução nem revela raciocínio interno.
8. API e operação: códigos, idempotência, fila/claim/heartbeat, SSE/snapshot, cache, quotas, persistência, backup/restauração e exportação. Distinguir worker observado de LLM conectada.
9. Concluir cada achado com evidência, impacto, hipótese causal, responsável, correção mínima, teste de regressão e critério mensurável de reavaliação.

## Entregas propostas, sequenciais

1. Dicionário de dados e métricas: unidade, fonte, denominador, ausência, retenção, responsável e decisão de cada indicador. Backend e Metodologia aprovam definições.
2. A9: exportação versionada das tabelas canônicas, incluindo benchmark, tentativas tardias, conflitos e replays; snapshot consistente e reconciliação com reservas/artefatos. Aceite: nenhuma tentativa elegível omitida ou duplicada, falhas de coleta explicitadas, testes sintéticos e PostgreSQL.
3. A7: confrontar declaração do agente com chamadas e artefatos reais; manter resultado científico independente. Aceite: identidades inventadas/estrangeiras recusadas e divergências expostas.
4. Instrumentação HTTP e fases: request_id e correlação com run/chamada/tentativa, rota parametrizada, status, duração e fase; spans de banco/commit/entrega somente onde necessários. Integrar A0/A3/A5/A6 sem duplicar suas entregas. Não escolher plataforma de observabilidade antes de definir o mínimo necessário.
5. Relatório analítico inicial: tabela de qualidade dos dados, confiabilidade, desempenho, recuperação e resultado por tarefa. Começar com exportação e agregação reproduzível; painel visual vem depois das métricas validadas.
6. Piloto controlado: uma melhoria por experimento, tarefas de desenvolvimento pareadas, parâmetros congelados e critérios de sucesso/regressão definidos antes da rodada. Preservar tarefas finais e registrar todos os resultados.

## Limites e governança

Backend mede execução; Documentos avalia corpus/recuperação; equipes dos agentes fornecem adaptadores e topologia; Infra valida ambiente/operação; Metodologia define sucesso e comparação. Não inferir qualidade semântica de HTTP 200, número de chamadas ou existência de artefato.

IDs de correlação ficam em registros/traces, não como dimensões ilimitadas de métricas agregadas. Não registrar tokens, credenciais, prompts, argumentos completos ou documentos em logs operacionais. Hash não anonimiza texto de baixa entropia. Acesso ao conteúdo para avaliação exige armazenamento privado, finalidade e retenção explícitas. Medir também custo e falhas da própria instrumentação.

Este roteiro complementa o plano vigente; não libera automaticamente blocos, implantação, migrações ou publicação. Não foi criada skill adicional: o roteiro específico do projeto pode ser aplicado nas auditorias sem duplicar as skills existentes de revisão e verificação.

## Complemento de 29/10/2026 — roteamento, avaliação e refinamento

Novas referências: cinco fotografias fornecidas pelo responsável, incluindo as páginas visíveis 129, 131, 233 e 282. Os exemplos de código são ilustrações conceituais; não constituem contrato de API ou comprovação de compatibilidade com versões instaladas. As regras abaixo são propostas de auditoria, não funcionalidades já implementadas.

### Roteamento e término

- Desenhar nós, transições permitidas, pontos de decisão e junções antes de avaliar a execução. Exigir critérios de entrada/saída por nó e tratamento de estado incompleto ou categoria desconhecida.
- Testar cada roteador com casos válidos, ambíguos e inválidos. Verificar se a transição observada é permitida e se o resultado intermediário atende ao contrato do próximo nó.
- Identificar nós inalcançáveis, ciclos sem progresso e caminhos sem término. Caminho sem nó terminal deve ter saída explícita por erro, cancelamento ou orçamento. Limite de profundidade sozinho não comprova correção nem término bem-sucedido.
- Em ramificações, explicitar quais resultados são obrigatórios, quando a junção pode prosseguir, como tratar falha parcial e como evitar processamento duplicado.
- Usar a topologia mais simples que atenda à tarefa. Acrescentar nós, ramificações ou paralelismo somente com benefício esperado e experimento que avalie qualidade, latência e custo.
- Backend fornece execução e evidências; definição da topologia e seleção das ferramentas pertencem aos adaptadores. Não impor um grafo idêntico a Hermes e LangGraph nem pressupor capacidades de runtimes ainda não homologados.

### Matriz de testes de cada ferramenta

| Dimensão | Casos e evidência exigida |
| --- | --- |
| Contrato | Entrada válida, limites, tipos errados, campos ausentes/extras, resposta inválida e contexto estrangeiro |
| Dados | Vazio, formato válido alternativo, Unicode, corrupção, versão divergente e corpus parcial |
| Dependências | Banco indisponível, resposta lenta, timeout, falha antes/depois do commit, perda da resposta e reconexão |
| Efeitos | Autorização revogada, concorrência, idempotência, rollback, conferência independente de artefato e hash |
| Desempenho | Latência por fase, recursos e contenção sob carga definida, incluindo falhas; registrar ambiente e amostra |
| Composição | Saída de busca usada na leitura/evidência, requisito usado na pendência e recibo conferido como artefato; erros intermediários não podem virar sucesso silencioso |

Doubles permitem reproduzir falhas específicas, mas não substituem integração HTTP real, PostgreSQL e homologação dos adaptadores. A massa precisa ser sintética e versionada. Saídas determinísticas exigem igualdade nas condições declaradas; componentes estocásticos exigem avaliação por critérios e distribuição, sem presumir que uma única resposta boa é suficiente.

### Classificação para orientar a melhoria

Separar: escolha inadequada de ferramenta; argumentos inválidos; capacidade ausente; falha interna da ferramenta; falha de infraestrutura; incompatibilidade de entrada/saída entre etapas; roteamento incorreto; qualidade semântica insuficiente. Um código HTTP isolado não identifica todas essas causas. Indicar quem classificou, a evidência e o grau de certeza.

- Escolha inadequada: revisar catálogo/descrições e integração do adaptador com as equipes responsáveis.
- Argumentos inválidos: revisar schema, exemplos e transformação de dados; preservar validação estrita.
- Capacidade ausente: verificar se é lacuna real do produto antes de propor uma tool nova.
- Falha interna: corrigir a camada responsável, com reprodução e regressão.
- Incompatibilidade entre etapas: tornar explícitos tipos, identidade, versão, cardinalidade e semântica transferidos.
- Falha de infraestrutura: melhorar limites, recuperação ou ambiente segundo evidência de execução.

Mudanças de prompt/modelo são experimentos das equipes de agentes e Metodologia; otimização de ferramenta ou adoção de frameworks citados nas imagens não fica automaticamente autorizada.

### Indicadores adicionais e fechamento

Registrar, quando houver instrumentação suficiente: transições inválidas / transições observadas; execuções encerradas / execuções iniciadas, distinguindo sucesso, falha, timeout e ainda ativas; iterações por tarefa; junções com falha parcial; falhas de composição / transferências observadas. Cobertura de testes de rotas deve declarar o conjunto de transições esperado; não inferir cobertura completa apenas dos caminhos usados em produção.

Cada mudança deve acrescentar a reprodução do defeito ao conjunto de regressão, executar os testes pertinentes e concluir as verificações completas exigidas pelo projeto. Comparar antes/depois sob mesmas condições, registrando também regressões de qualidade, custo e tempo. Aprovar a melhoria somente quando o critério previamente definido for atendido; ausência de ganho sustenta simplificar ou descartar a mudança.

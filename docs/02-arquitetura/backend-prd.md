# PRD — Backend, tools e chat experimental

Data: 24/10/2026. Responsável: Backend & Tools. Estado: implementação local,
pendente de revisão conjunta e homologação dos agentes reais.

## Objetivo e participantes

Oferecer seis ferramentas equivalentes a Hermes e LangGraph. Um participante
interno seleciona processo e executor, envia uma tarefa e acompanha resposta,
fontes e gravações. O backend executa operações; o agente decide quais chamar.
O sistema trabalha sobre exportações manuais, sem integração com o SEI institucional.

O participante não precisa de login no piloto em loopback. Um UUID pseudônimo
identifica suas conversas para análise, sem comprovar identidade. Operador técnico
e worker continuam autenticados no servidor. Não existe isolamento de pessoas
que compartilham a mesma credencial técnica.

## Fontes e precedência

- Guia do projeto enviado pelo responsável, 23 páginas, proposta de 17/09/2026.
  SHA-256 da cópia recebida:
  `5e2b1e0a763477bc8cacbb25b2f4faccc89b80af0a4cf53d42fe35120333a846`.
  As seções técnicas coincidem com o [guia arquivado](../06-arquivo/Guia_Projeto_SEI_Hermes_LangGraph.pdf);
  diferenças textuais nas páginas 1 e 4 retiram atribuição nominal da coordenação.
- [Backlog](../01-overview/backlog.md), tarefas 2.1–2.5, e
  [responsabilidades de Backend](../03-equipes/backend.md).
- [Contratos](../../contracts/README.md), [arquitetura](architecture.md) e
  [protocolo metodológico](../../evaluation/protocol.md).
- Decisões do responsável nesta tarefa: tools primeiro; frontend de chat;
  memória por conversa; participante sem login; agentes entregues pelas equipes;
  ingestão de arquivos numa segunda etapa; trabalho local, sem publicação.

Exemplos do PDF são didáticos, não APIs obrigatórias nem evidência de implantação.
Contratos executáveis definem as rotas vigentes. A proposta de duas camadas,
estimativas de custo e marcos históricos não ampliam esta entrega.

## Requisitos e rastreabilidade

| ID | Requisito / origem | Aceite e evidência |
| --- | --- | --- |
| B01 | Seis tools REST comuns; guia pp. 8–11 | Catálogo fechado, schemas sem contexto privilegiado e endpoints exercitados nos testes de tools/integração. |
| B02 | Consulta, inventário, busca e páginas; guia pp. 6/8 | Filtros antes do limite; fontes válidas; cobertura parcial e busca vazia não viram afirmação de ausência. |
| B03 | Checklist versionado; guia pp. 8/10 | Importação administrativa imutável; requisito de pendência deve pertencer à versão. |
| B04 | Escritas confirmadas; guia pp. 9–11 | Transação, constraint única, replay idêntico, conflito diferente e conferência independente de conteúdo/hash. |
| B05 | Execução autenticada; guia pp. 3/8 | Modelo não altera contexto; worker precisa de credencial técnica e reserva ativa. |
| B06 | Persistência e recuperação; guia pp. 14–16 | Migrações preservam corpus; PostgreSQL valida concorrência e restauração. |
| B07 | Chat e memória; decisão do responsável | Segunda pergunta recebe somente interações concluídas da conversa; reinício preserva histórico. |
| B08 | Acompanhamento; decisão do responsável | Eventos persistidos, SSE retomável e resposta final consistente com deltas. |
| B09 | Participante para Evaluation; decisão do responsável | UUID associado à conversa, ausente do contexto do modelo; exportação JSONL sem conteúdo por padrão. |
| B10 | Agentes reais; guia pp. 12–14 | Cada adaptador executa consulta e escrita, falta de informação e recuperação controlada pela mesma API. |

## Jornadas

1. Abrir chat local, escolher processo/corpus e executor disponível, enviar texto.
2. Acompanhar fila, execução e resposta; abrir fontes e artefatos confirmados.
3. Enviar pergunta de continuidade; recarregar e recuperar a mesma conversa.
4. Criar outra conversa para mudar processo ou executor.
5. Operador exporta registros privados para Evaluation, selecionando participante
   ou conversa. Textos só entram com opção explícita.

## Entregas e dependências

Ordem: contratos/persistência mínima → leituras → escritas → integração HTTP dos
agentes → chat/memória → validação e operação. O código local v0.2 é reaproveitado
após testes; o trabalho original permanece preservado.

Backend entrega API, tools, memória, fila, cliente e worker comum, frontend e
registros. Documentos/RAG entrega corpus e recuperação; as equipes Hermes e
LangGraph entregam adaptadores; Infra fornece ambiente; Metodologia homologa
checklists, tarefas e interpretação dos registros.

O piloto completo depende de URL/versão oficial do Hermes, adaptadores instalados,
modelo/endpoint autorizado e configuração privada. Simulador não satisfaz B10.
Falhas e verificações indisponíveis devem constar no relatório, sem marcar aceite.

## Fora do escopo e próxima etapa

Sem implementação de agentes, OCR, embeddings, indexação, cache experimental,
painel comparativo, avaliação científica, publicação ou deploy.
Próxima etapa: especificar com RAG upload, limites de arquivos, processamento
assíncrono, publicação de corpus e falhas. Nenhuma rota de upload está prometida
como disponível nesta versão.

Ver [TDD](backend-tdd.md), [ADRs](../05-decisoes/README.md) e
[operação](../04-operacoes/chat.md).

# Metodologia e avaliação (Evaluation)

Integrantes: 4 | Monitor: Gustavo Antônio. Branch: `team/metodologia` (ou `feat/evaluation`).  
Consulte o [Guia de Onboarding e Operação](guia-onboarding-operacao.md) ([PDF](Guia_Onboarding_Metodologia_Evaluation.pdf)).

- **Monitor:** Gustavo Antônio
- **Integrantes:**
  - Nelson da Rocha Bomfim Neto (3° semestre eng. de software)
  - Sarah Leticia da Silva (3° semestre de sistemas de informação)
  - João Pedro Silva dos Santos (5° semestre eng. de software)
  - Isaac Joaquim (5° semestre eng. de software)

## Objetivo e responsabilidades

Definir tarefas, rubricas e métricas antes da coleta e produzir comparação reproduzível.

Desenho pareado, desenvolvimento versus avaliação final, gabaritos, evidências, métricas, análise de incerteza/erros e rastreabilidade do harness.

Limites: Não inventar resultados nem ajustar rubrica depois de ver vencedores. Não considerar sucesso declarado como escrita confirmada ou repetições como observações independentes.

## Entradas, saídas e dependências

Recebe corpus/versões e registros dos executores; entrega protocolo pré-definido, tarefas e critérios, depois análise baseada em evidências reais.

Documentos valida fontes; Backend comprova persistência; agentes instrumentam chamadas; Infra mede ambiente; Coordenação decide corpus, especialista e veículo.

Pastas: evaluation/, contratos de ExperimentRun em revisão conjunta, documentação científica.

## Estudar e executar

Desenho experimental pareado, rubricas, avaliação cega, unidades de análise, medidas repetidas, latência/tokens/custo e análise de erros.

Primeiro siga [instalação](../00-comece-aqui/01-inicio-rapido.md) e execute a demo. Comando da frente:

```sh
uv run --locked python -m scripts.dev check
```

Use `uv run --locked python -m scripts.dev check` antes do PR.

## Primeiras tarefas

1. Revisar a tarefa sintética de desenvolvimento em evaluation/tasks.json.
2. Escrever mais duas tarefas com resultado observável, fontes e rubrica antes de executar agentes.
3. Definir plano de amostragem/repetições e reconciliar 360 versus 1.080 execuções dos PDFs com a coordenação.

## Quadro de distribuição de tarefas da equipe (Novembro 2026)

Para garantir a entrega completa do framework de avaliação do benchmark até meados de novembro de 2026, as frentes de trabalho foram distribuídas e operacionalizadas entre os integrantes da equipe e o Agente Evaluation:

| Integrante | Responsabilidades e Entregas | Status / Entregáveis |
|---|---|---|
| **Nelson da Rocha Bomfim Neto** | Desenvolvimento das rubricas determinísticas por regex para respostas factuais e homologação inicial de gabaritos (`DEV-001` a `DEV-006`). | Entregue no commit `219d9d6` (`origin/task/evaluation-tasks-piloto`). Integrado e estendido para DEV-001 a DEV-015 em `evaluation/rubric_auto.py`. |
| **Isaac Joaquim** | Implementação do harness de execução pareada (`run_paired_adapters`), contrabalanceamento de ordem de execução e cálculo de score composto ponderado por perfil de caso de uso. | Implementado em `evaluation/runner.py` e `evaluation/metrics.py` com perfis (`operacional`, `auditoria`, `balanceado`). |
| **João Pedro Silva dos Santos** | Estruturação do protocolo de dupla avaliação cega, mascaramento determinístico por SHA-256 (`prepare_blind_packet`), concordância Kappa de Cohen e formulário de submissão. | Implementado em `evaluation/rubric.py`, `evaluation/blind_review.md` e `evaluation/formulario_avaliacao_cega.md`. |
| **Sarah Leticia da Silva** | Curadoria das tarefas no catálogo `evaluation/tasks.json`, definição de taxonomia de categorias (`extracao_direta`, `busca_vazia`, `sintese_cruzada`), níveis de dificuldade e preparação do split final. | Catálogo das 15 tarefas de desenvolvimento homologado em `evaluation/tasks.json` e `evaluation/gabaritos.md`. |
| **Agente Evaluation (Supervisão/Engenharia)** | Resolução de conflito arquitetural entre rubrica cega e regex, desacoplamento em `rubric.py` e `rubric_auto.py`, expansão para as 15 tarefas piloto (`DEV-001` a `DEV-015`), ajuste de ausência de custo no score composto, runner integrado e testes automatizados. | Totalmente funcional e validado com 100% de cobertura nos testes dirigiros (`tests/evaluation`). |

### Implementações assumidas pelo Agente Evaluation

1. **Desacoplamento e Resolução de Conflito de Rubricas:**
   - Manutenção de `evaluation/rubric.py` com as funções de rubrica manual, avaliação cega (`evaluate_rubric`, `prepare_blind_packet`, `compute_blind_agreement`) e validação de política de escrita (`check_write_policy`).
   - Criação de `evaluation/rubric_auto.py` com avaliação determinística estrita por regex, retornando `RubricResult` e preenchendo `ExperimentRun.verified_success` e `evaluator="deterministic-rubric-v0.1"`.
2. **Cobertura Integral das 15 Tarefas de Desenvolvimento:**
   - Implementação das funções de avaliação para `DEV-001` até `DEV-015`, respeitando o [gabarito homologado](../../evaluation/gabaritos.md) e regras epistêmicas de exportação parcial.
3. **Harmonização do Runner (`evaluation/runner.py`):**
   - Propagação correta dos parâmetros `task_id`, `split` e `repetition` para adaptadores.
   - Avaliação determinística imediata de respostas finais fornecidas pelos adaptadores (`final_response` / `last_response`).
   - Criação preventiva e idempotente de `results_dir`.
4. **Renormalização do Score Composto (`evaluation/metrics.py`):**
   - Em `compute_composite_score`, ausência de custo (`cost_usd is None`) redistribui proporcionalmente os pesos entre as métricas observadas (`sr`, `compliance`, `tua`, `latency`), eliminando benefício artificial de nota máxima para dados ausentes.

## Critério de conclusão

Tarefas/rubricas versionadas antes da coleta, conjuntos separados, versões congeláveis e regra explícita de confirmação de resultado. Diff revisado, documentação coerente e limitações relatadas. Marque tarefas concluídas somente com evidência.

[Backlog conjunto](../01-overview/backlog.md) · [Git](../00-comece-aqui/02-fluxo-git.md) · [Contratos](../../contracts/README.md)

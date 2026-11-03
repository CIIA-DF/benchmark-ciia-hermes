# ADR 003 — provedor de inferência OpenRouter e benchmark em duas camadas

Data: 03/11/2026. Situação: decisão aprovada pela coordenação (Gustavo Antônio / monitores).

Complementa a [ADR 001](001-base-inicial.md) e formaliza o desenho experimental da [proposta de duas camadas](../02-arquitetura/proposta-benchmark-duas-camadas.md) e do [protocolo de avaliação](../../evaluation/protocol.md).

## Contexto

O projeto possui um teto orçamentário rígido de **$25 USD** concedido pela coordenação para o consumo de APIs de modelos de linguagem durante todo o ciclo do projeto (desenvolvimento, validação e benchmark final até 10/12/2026). Não há infraestrutura local de GPU dedicada capaz de servir modelos de 70B com estabilidade on-premises.

Além da restrição orçamentária, a metodologia exige:
1. **Paridade experimental estrita (GEMINI.md §7):** Hermes e LangGraph devem consumir rigorosamente o mesmo endpoint, versão de modelo e hiperparâmetros.
2. **Isolamento de variáveis:** Separar a avaliação de eficiência dos **orquestradores de agentes** (loops, tool-calling e tratamento de buscas vazias) da avaliação de capacidade intrínseca dos **modelos de linguagem** no domínio de processos administrativos do SEI (conformidade LGPD vs. padrão-ouro comercial).

## Decisão

### 1. Gateway Unificado e Contrato de Configuração

Fica definido o **OpenRouter** (`https://openrouter.ai/api/v1`) como o gateway unificado de inferência para todas as frentes (`team/hermes`, `team/langgraph` e `team/metodologia`).

A comunicação respeita a interface padronizada [`ModelConfig`](../../agents/interface.py):
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `LLM_API_KEY`: fornecida via variável de ambiente privada (nunca versionada no Git).
- `LLM_TIMEOUT_SECONDS=60.0`.
- Hiperparâmetros congelados para o benchmark: `temperature=0.0`, `seed=42` (quando suportado) e parada determinística.

### 2. Camada 1: Benchmark de Orquestradores (Hermes vs. LangGraph)

- **Objetivo:** Avaliar exclusivamente o overhead, a robustez algorítmica, o consumo de ferramentas e a resiliência a 404/vazio dos frameworks de agente.
- **Modelo Fixo e Simétrico:** `openai/gpt-4o-mini`.
- **Justificativa:** Alta velocidade, aderência estrita a function calling/JSON schema e custo ultrabaixo (~$0,004 USD por execução completa de 20k tokens).
- **Volumetria Prevista:** 15 tarefas × 2 orquestradores × 5 repetições = **150 execuções**.
- **Custo Projetado da Camada 1:** **~$0,60 USD**.

### 3. Camada 2: Benchmark de Modelos de Linguagem no Domínio SEI

- **Objetivo:** Responder se modelos abertos/econômicos (aptos à soberania de dados/LGPD no GDF) atingem paridade de fundamentação e citação exata de páginas em relação ao padrão-ouro de mercado.
- **Orquestrador Fixo:** Um único harness/orquestrador padronizado consumindo o catálogo comum de 6 ferramentas REST (`ToolClient`).
- **Modelos Avaliados (4 competidores):**
  1. `meta-llama/llama-3.3-70b-instruct`: open-weights de alta capacidade (~$0,008 USD/run).
  2. `deepseek/deepseek-chat` (DeepSeek-V3) ou `qwen/qwen-2.5-72b-instruct`: alta capacidade analítica de baixo custo (~$0,006 USD/run).
  3. `openai/gpt-4o-mini`: modelo proprietário enxuto e econômico (~$0,004 USD/run).
  4. `anthropic/claude-sonnet-4.6` (ou `claude-sonnet-4.5`): **Padrão-Ouro (*Gold Standard*)**, precificado em $3,00 / $15,00 por milhão de tokens (~$0,085 USD/run).
- **Estratégia de Amostragem do Sonnet:** Para blindar o teto de $25 USD, o Sonnet é reservado estritamente para uma amostragem controlada de avaliação (ex.: 15 tarefas × 3 repetições = 45 runs, custando ~$3,82 USD).
- **Custo Projetado da Camada 2:** **~$4,63 USD**.

### 4. Fase de Desenvolvimento e Testes Locais

- As equipes de desenvolvimento devem usar `meta-llama/llama-3.3-70b-instruct:free` (ou modelos com variante gratuita na OpenRouter) ou rodadas pontuais com `gpt-4o-mini`.
- Todo adaptador (`HermesAdapter` e `LangGraphAdapter`) deve implementar teto rígido de iterações (`max_turns <= 10`) e timeout por chamada para prevenir loops infinitos e consumo indevido de saldo.

## Planejamento Orçamentário Consolidado

| Etapa | Volume Estimado | Custo Projetado |
| :--- | :--- | :--- |
| **Camada 1 (Hermes vs. LangGraph com GPT-4o-mini)** | 150 execuções | ~$0,60 USD |
| **Camada 2 (Modelos vs. Modelos com Sonnet 4.6)** | 180 execuções | ~$4,63 USD |
| **Desenvolvimento e Testes das Equipes** | ~500 chamadas | ~$2,00 USD |
| **Margem de Contingência / Retestes** | Variável | ~$3,00 USD |
| **Custo Total Previsto:** | **~830 runs** | **~$10,23 USD** |
| **Saldo Preservado da Conta ($25 USD):** | | **+$14,77 USD (Margem de ~59%)** |

## Consequências

- Nenhum adaptador pode conter chaves codificadas ou chamar diretamente endpoints proprietários fora do padrão `ModelConfig`.
- O modelo `anthropic/claude-sonnet-4.6` fica proibido para depuração e testes diários, sendo liberado apenas na rodada oficial de congelamento da Camada 2.
- O arquivo `.env.example` passa a documentar a OpenRouter como URL padrão para inferência externa.
- A equipe de Metodologia e Avaliação utilizará esse teto e divisão de camadas para formalizar os gabaritos e a coleta de dados de `ExperimentRun`.


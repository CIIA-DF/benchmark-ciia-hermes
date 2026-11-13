# Landing Page e Painel de Resultados do Benchmark CIIA/UnDF

Pasta dedicada ao site institucional, vitrine científica e leaderboard do **Benchmark CIIA/UnDF: Hermes vs. LangGraph no SEI**.

---

## 1. Estrutura de Arquivos

- `index.html`: Landing page principal do projeto com visão executiva, formulação do problema, paridade estrita e estrutura das 6 equipes.
- `resultados.html`: Painel oficial de resultados em produção (com estrutura de matriz pareada aguardando consolidação final dos dados experimentais), contendo as 14 configurações em avaliação, duelo metodológico local vs. nuvem e regras das 4 partes do protocolo.
- `ciia_logo.png`: Logo oficial do Centro Integrado de Inteligência Artificial (CIIA), integrado no topo da navegação de ambas as páginas.

---

## 2. Conteúdo e Alinhamento Científico

As páginas refletem fielmente as diretrizes do projeto definidas em [AGENTS.md](../AGENTS.md) e [GEMINI.md](../GEMINI.md):

1. **Pergunta Científica Central**: Isolamento da orquestração (Hermes ReAct vs. LangGraph State Graph) vs. capacidade do modelo.
2. **Regra de Ouro da Paridade**:
   - Mesmo barramento (`ToolClient`) e os mesmos 6 endpoints REST da API em FastAPI.
   - Sem roteiro pré-programado ou atalhos heurísticos.
   - Sucesso verificado $\neq$ sucesso declarado (auditoria estrita de evidências documentais por página física e offset).
   - Isolamento de contexto por `run_id` (UUID único por execução).
3. **Desenho Experimental em Duas Fases**:
   - **Fase 1 (Prioridade)**: 360 execuções controladas (60 tarefas $\times$ 2 orquestradores $\times$ 3 repetições sob o mesmo modelo).
   - **Fase 2 (Soberania)**: 1.080 execuções comparando modelos locais (Qwen 2.5, Llama 3.1) vs. modelos de nuvem comercial (GPT-4o, Claude 3.5) avaliando Custo por Tarefa Concluída (CTCE).
4. **Estrutura das 6 Equipes**:
   - Equipe 01: Data & RAG (Documentos)
   - Equipe 02: Backend & Tools
   - Equipe 03: Hermes
   - Equipe 04: LangGraph
   - Equipe 05: AI Infra
   - Equipe 06: Metodologia & Evaluation
5. **Salvaguardas Institucionais & Transparência**:
   - Operação 100% sobre exportações manuais tratadas/sintéticas do SEI.
   - Zero conexão com o SEI real em produção.
   - Conformidade com a LGPD e ausência total de dados fictícios ou falsos vencedores: o painel opera em modo de produção/espera até a homologação final dos testes.

---

## 3. Como Visualizar Localmente

### Opção A — Abertura Direta no Navegador

Abra o arquivo `landing/index.html` ou `landing/resultados.html` diretamente em qualquer navegador moderno.

### Opção B — Servidor Local Rápido (Python)

No terminal, a partir da raiz do repositório:

```bash
uv run --locked python -m http.server 3001 --directory landing
```

- Visão Geral: [http://localhost:3001/index.html](http://localhost:3001/index.html)
- Painel Oficial de Resultados (Em Produção): [http://localhost:3001/resultados.html](http://localhost:3001/resultados.html)

---

## 4. Roteiro de Integração com o Portal Next.js (`portal/`)

O repositório já possui uma aplicação Next.js configurada em [`portal/`](../portal/README.md) voltada ao deploy contínuo via VPS Hostinger ([deploy-vps-hostinger.md](../docs/04-operacoes/deploy-vps-hostinger.md)).

Atualmente, `portal/app/page.tsx` realiza um redirecionamento imediato para `/team` (leitor da documentação das equipes). A evolução arquitetural recomendada é:

- `portal/app/page.tsx`: Landing page principal (baseada em `landing/index.html`).
- `portal/app/resultados/page.tsx`: Leaderboard interativo (baseado em `landing/resultados.html`).
- `portal/app/team`: Documentação técnica das equipes (mantida intacta).

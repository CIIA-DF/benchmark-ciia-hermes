# Protocolo Experimental: Congelamento Metodológico e Blind Test

Este documento estabelece o protocolo científico, o controle de integridade e as regras de execução do benchmark comparativo pareado entre os executores **Hermes** e **LangGraph**, operando sobre exportações do SEI em ambiente experimental controlado.

---

## 1. Pergunta Científica e Objetivo

**Pergunta de pesquisa:** Sob idêntico corpus documental sintético, idêntico catálogo de ferramentas, mesmo modelo de linguagem fundacional e mesmo orçamento de inferência, como diferem os executores Hermes e LangGraph em termos de:
1. Sucesso verificado da tarefa (atendimento integral a critérios críticos de aceitação);
2. Fundamentação factual (citação exata de documento e página física de comprovação);
3. Limitações de integridade reconhecidas (não concluir ausência no processo original quando a exportação for parcial);
4. Ausência de ações indevidas (não emitir minutas ou pendências para tarefas exclusivas de consulta);
5. Latência, consumo de tokens e custo computacional.

O **Congelamento Metodológico** tem como objetivo blindar o estudo contra viés de confirmação (*confirmation bias*), ajuste oportunista de parâmetros (*overfitting* de prompts) e contaminação de dados (*data leakage*), fixando previamente todas as condições experimentais antes do início das medições oficiais.

---

## 2. Condições do Congelamento Metodológico

As condições técnicas vigentes no momento do congelamento estão formalizadas no manifesto [`evaluation/freeze_manifest.json`](freeze_manifest.json). O congelamento abrange:

1. **Código-fonte e Configurações:** Commit exato da árvore de avaliação (`219d9d6` na branch `task/evaluation-tasks-piloto`).
   *Nota de Rastreabilidade e Ambiguidade:* As implementações completas dos adaptadores encontram-se em branches específicas da equipe (`origin/feat/hermes` / `origin/team/hermes` e `origin/task/langgraph-grafo`) e ainda não foram consolidadas na branch principal (`main`). Para a execução final oficial do benchmark, será necessário um commit unificado em `main`.
2. **Ambiente e Dependências:** Fixação determinística das dependências e versões no arquivo `uv.lock`, auditado via hash criptográfico SHA-256 (`1b4351948d19b621fdbd0c4ab4004e72379dde99c76cc803b42be66f698afab0`).
3. **Prompts dos Agentes:** Congelamento do hash SHA-256 dos *system prompts* de cada adaptador:
   - **Hermes:** `4c3a60046f0c743fd29f60e746ea91565721387d9c6b745e196fdc801653d976` (`origin/feat/hermes:agents/hermes/adapter.py`).
   - **LangGraph:** `00010522357b92625845289cbcafbf45281b42f39a9799a51aa89a9390491200` (`origin/task/langgraph-grafo:agents/langgraph/graph.py`).
4. **Corpus e Requisitos:** Corpus estritamente sintético (`corpus_version: "synthetic-v1"`, `process_id: "PROC-DEMO-001"`, `requirements_version: "demo-v1"`). É vedado o uso de documentos, processos ou dados reais do SEI.
5. **Rubricas de Avaliação:** Rubricas determinísticas pré-fixadas e testadas em `evaluation/rubric.py`.

---

## 3. Separação dos Conjuntos: dev_set e test_set_secret

Para assegurar validade científica externa e evitar contaminação do benchmark, o catálogo de tarefas é estruturado em dois subconjuntos estanques:

### 3.1. Conjunto Público de Desenvolvimento (`dev_set`)
- **Arquivo:** [`evaluation/tasks.json`](tasks.json).
- **Finalidade:** Ajuste técnico dos agentes, depuração de integrações de ferramentas, verificação de conformidade do formato de resposta e testes em simulação.
- **Composição atual:** 15 tarefas piloto homologadas (`DEV-001` a `DEV-015`), todas marcadas com `"split": "development"`. O catálogo cobre extração direta, busca vazia com ressalva de exportação parcial e síntese cruzada sobre o corpus sintético `PROC-DEMO-001`.
- **Visibilidade:** Público e versionado no Git.

### 3.2. Conjunto Reservado Cego (`test_set_secret`)
- **Arquivo / Diretório:** `evaluation/test_set_secret/` (contendo `tasks.json`, `processes.json`, `documents.json` e `ground_truth.json`).
- **Finalidade:** Avaliação final cega (*blind test*) de generalização e desempenho comparativo entre Hermes e LangGraph sobre cenários inéditos.
- **Composição:** Exatamente 5 tarefas cegas (`BLIND-001` a `BLIND-005`), com `"split": "test_set_secret"`. As tarefas abrangem extração direta com múltiplos atributos, identificação de atos ausentes com ressalva, cruzamento documental entre processo e nota técnica, análise de pendência interna sem escrita indevida, e síntese de vigência contratual.
- **Corpus Sintético Reservado:** Processos e documentos 100% sintéticos e isolados (`PROC-BLIND-001`, `PROC-BLIND-002`, `DOC-BLIND-001`, `DOC-BLIND-002`, `DOC-BLIND-003`), sem reuso de dados do `dev_set` nem uso de dados reais do SEI.
- **Regras de Acesso e Preservação:**
  1. O diretório e arquivos do conjunto secreto são estritamente ignorados pelo `.gitignore` e mantidos fora do versionamento público.
  2. Nenhum conteúdo de enunciado, documento ou resposta esperada é exposto em arquivos públicos ou logs acessíveis aos agentes durante a fase de desenvolvimento.
  3. A injeção das tarefas secretas ocorre exclusivamente no ambiente de execução oficial da avaliação cega.
  4. O gabarito factual e critérios de aceitação permanecem arquivados em `evaluation/test_set_secret/ground_truth.json` para conferência exclusiva dos avaliadores.

---

## 4. Desenho Experimental e Quantidade de Repetições

### 4.1. Repetições Pareadas
- **Número de repetições:** $N = 5$ rodadas pareadas por modelo e por tarefa.
- **Unidade de análise primária:** O par `(Hermes, LangGraph)` avaliado sobre a mesma tarefa $T_i$ e mesma repetição $k \in \{1, 2, 3, 4, 5\}$.
- **Condições idênticas de inferência:**
  - Mesmo modelo de fundação e mesma versão de pesos;
  - Mesmo endpoint de inferência;
  - Mesmos hiperparâmetros de decodificação (temperatura fixada em 0.0 para maximizar determinismo);
  - Mesmo limite máximo de turnos de ferramentas (`max_tool_rounds = 10`);
  - Limpeza e reinicialização de estado entre rodadas (isolamento estanque por `run_id`, sem reutilização de sessões ou memória residual).

### 4.2. Tratamento Estatístico
- Repetições de uma mesma tarefa configuram **medidas repetidas (correlacionadas)** e não serão tratadas como observações independentes.
- A análise comparativa agregará a taxa de sucesso verificado e o custo computacional no nível de tarefa antes de testes de hipótese pareados (e.g., teste de postos sinalizados de Wilcoxon ou modelos mistos).

---

## 5. Preservação do Isolamento do Conjunto Reservado (Blind Test)

Para assegurar a blindagem metodológica do `test_set_secret`:

1. **Isolamento de Versionamento:** Entradas no `.gitignore` impedem a inclusão acidental do arquivo ou pasta de tarefas cegas no repositório Git.
2. **Isolamento de Execução:** Os executores dos agentes nunca devem ser disparados contra o `test_set_secret` durante as fases de desenvolvimento, depuração ou testes unitários locais.
3. **Proteção em Logs e Relatórios:** Os enunciados, gabaritos e critérios das tarefas cegas não devem ser exportados em logs públicos, artefatos de CI ou relatórios abertos de execução (`ExperimentRun`).
4. **Sem Vazamento em Prompts:** Nenhuma informação factual ou contraexemplo extraído das tarefas cegas pode ser incorporado aos prompts ou instruções dos agentes.

---

## 6. Procedimento de Verificação de Hashes e Versões

Antes de qualquer execução oficial da bateria de testes, deve-se auditar o alinhamento com o manifesto:

1. **Verificação de Dependências:**
   ```sh
   # Conferir se o hash do uv.lock confere com o manifesto
   python -c "import hashlib, json; manifest = json.load(open('evaluation/freeze_manifest.json')); lock_hash = hashlib.sha256(open('uv.lock', 'rb').read()).hexdigest(); assert lock_hash == manifest['methodological_freeze']['environment']['uv_lock_sha256'], 'uv.lock divergente!'"
   ```
2. **Verificação dos Prompts:**
   Conferir se o `SYSTEM_PROMPT` do agente sob teste possui o mesmo SHA-256 declarado no manifesto.
3. **Verificação da Integridade dos Testes:**
   Executar a suíte de testes de integridade do manifesto:
   ```sh
   uv run pytest tests/evaluation/ -q
   ```

---

## 7. Condições que Impedem Alterações Posteriores ao Congelamento

Uma vez iniciado o processo de avaliação oficial contra o conjunto reservado:

1. **Imutabilidade Rígida:** É terminantemente proibido:
   - Alterar o texto dos prompts dos agentes;
   - Modificar a arquitetura, arestas ou loop ReAct dos agentes;
   - Alterar critérios de aceitação, expressões regulares ou funções em `evaluation/rubric.py`;
   - Substituir tarefas ou alterar o gabarito das tarefas cegas;
   - Atualizar versões de dependências em `uv.lock`.
2. **Tratamento de Anomalias Críticas:** Caso uma falha técnica de infraestrutura (ex.: indisponibilidade do backend ou timeout de rede) impeça a conclusão da rodada:
   - O incidente deve ser formalmente documentado;
   - Caso seja indispensável aplicar uma correção de código, a versão congelada deve ser incrementada gerando um novo manifesto;
   - Todas as rodadas já executadas da tarefa afetada devem ser **integralmente descartadas para ambos os agentes**, reiniciando a coleta pareada daquela tarefa a partir da repetição 1. Não é permitido descarte unilateral ou seletivo de resultados.

---

## 8. Documentos de Referência

- [Manifesto de Congelamento Metodológico](freeze_manifest.json)
- [Catálogo de Tarefas de Desenvolvimento](tasks.json)
- [README de Metodologia e Avaliação](README.md)
- [Contratos de Modelos Experimentais](../contracts/models.py)
- [Diretrizes da Equipe de Metodologia](../docs/03-equipes/metodologia.md)

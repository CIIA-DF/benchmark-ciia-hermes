# Formulário de Avaliação Cega de Textos e Minutas (Task 6.4)

Instrumento oficial para auditoria humana duplo-cega de respostas administrativas, notas técnicas e minutas geradas pelos executores no benchmark SEI.

---

## Instruções ao Avaliador

1. Este formulário destina-se a avaliar um item identificado exclusivamente por um código anônimo `blind_id` (ex.: `BLIND-0001`).
2. O avaliador **não tem acesso** à identidade do executor (`hermes` ou `langgraph`), ao modelo de linguagem, custo ou número de iterações.
3. Não comunique suas notas ou impressões com outros avaliadores antes da etapa final de adjudicação.

---

## Ficha de Julgamento

| Campo | Preenchimento pelo Avaliador |
| :--- | :--- |
| **Identificador do Avaliador (`evaluator_id`):** | `EVAL-01` ou `EVAL-02` |
| **Código do Item (`blind_id`):** | `BLIND-XXXX` |
| **Data do Julgamento:** | `AAAA-MM-DD` |

---

### Seção 1: Checklist de Conformidade Factual Obrigatória (Binário: 0 ou 1)

*Nota: Falha em qualquer critério (nota 0) anula o sucesso verificado do agente.*

| # | Critério Crítico | Nota (0 ou 1) | Justificativa / Evidência Observada |
| :-: | :--- | :-: | :--- |
| **C1** | **`reference_valid`**: Cita expressamente o `document_id` e a página física exigidos pelo gabarito? | `[ 0 / 1 ]` | |
| **C2** | **`answer_supported`**: As declarações factuais decorrem estritamente da fonte indicada, sem inventar datas, valores ou pareceres? | `[ 0 / 1 ]` | |
| **C3** | **`completeness_acknowledged`**: Reconhece a completude parcial da exportação e que buscas vazias não comprovam inexistência no SEI original? | `[ 0 / 1 ]` | |
| **C4** | **`write_policy_respected`**: Absteve-se de registrar pendências/minutas indevidas em tarefas de consulta? | `[ 0 / 1 ]` | |

---

### Seção 2: Qualidade Textual e Redação Administrativa (Escala de 1 a 5)

*Apenas para respostas textuais, despachos e minutas elaboradas.*

| Dimensão | Descrição do Padrão | Nota (1 a 5) |
| :--- | :--- | :-: |
| **1. Clareza e Concisão** | Linguagem direta, formal, sem circunlóquios, prolixidade ou divagações. | `[ 1 - 5 ]` |
| **2. Precisão Terminológica SEI** | Emprego correto de termos da administração pública (despacho, processo, anexo, autuação). | `[ 1 - 5 ]` |
| **3. Fundamentação Normativa/Documental** | Conclusões atreladas às peças citadas, sem ilações jurídicas descabidas. | `[ 1 - 5 ]` |
| **4. Estrutura Textual do Despacho** | Apresenta relatório/síntese, análise e conclusão delimitada. | `[ 1 - 5 ]` |

*Escala: 1 = Muito Insuficiente, 2 = Insuficiente, 3 = Regular/Aceitável, 4 = Bom, 5 = Excelente.*

---

### Seção 3: Parecer e Observações Finais

- **Aprovação Global:** `[ ] SIM (verified_success = true)` \| `[ ] NÃO (verified_success = false)`
- **Observações / Anotações de Auditoria:**
  > *(Espaço para descrever eventuais alucinações, citações inexistentes ou pontos fortes da resposta)*

---

### Template JSON para Submissão Automatizada

```json
{
  "evaluator_id": "EVAL-01",
  "blind_id": "BLIND-0001",
  "checklist": {
    "reference_valid": 1,
    "answer_supported": 1,
    "completeness_acknowledged": 1,
    "write_policy_respected": 1
  },
  "text_quality": {
    "clarity": 5,
    "terminology": 5,
    "grounding": 5,
    "structure": 4
  },
  "verified_success": true,
  "notes": "Resposta precisa com citação da p. 2 de DOC-DEMO-001 e ressalva de exportação parcial."
}
```

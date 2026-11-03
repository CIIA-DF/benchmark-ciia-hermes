# Protocolo e Ficha de Avaliação Cega (Task 6.4)

Avaliação humana duplo-cega para respostas, despachos e minutas geradas pelos executores, conforme [protocolo experimental](protocol.md).

## 1. Regras de Ocultação (Blinding)

1. Antes da entrega aos avaliadores, todo registro `ExperimentRun` passa por `prepare_blind_packet` em [rubric.py](rubric.py).
2. Campos removidos do pacote de avaliação: `executor` (`hermes`/`langgraph`), `run_id`, `adapter_version`, `model`, `endpoint_id`, `latency_ms`, `cost_usd` e `tool_calls`.
3. A ordem dos itens é embaralhada deterministicamente por hash com semente fixa (`salt`) e cada item recebe apenas um código `BLIND-XXXX`.
4. O mapa `blind_id -> run_id` fica retido fora do pacote entregue aos avaliadores até o encerramento da consolidação.

## 2. Rubrica Binária Obrigatória (0/1)

Todo critério crítico deve ser pontuado como `0` (falha) ou `1` (cumprido). **Qualquer critério `0` resulta em `verified_success = false`.**

| Critério | `1` (Cumprido) | `0` (Falha / Bloqueio Crítico) |
| :--- | :--- | :--- |
| `reference_valid` | Cita exatamente o `document_id` e a página física (`page`) exigidos no gabarito da tarefa. | Omite documento/página ou cita documento/página inexistente ou incorreto. |
| `answer_supported` | Afirmações factuais sustentadas pelo texto da página citada, sem extrapolação ou alucinação. | Inventa fatos, datas, valores, nomes, pareceres ou normas ausentes nos autos exportados. |
| `completeness_acknowledged` | Reconhece explicitamente a completude da exportação (`partial`/`unknown`) e que busca vazia não prova inexistência no SEI original. | Trata exportação parcial como processo integral ou afirma que documento não localizado inexiste no processo original. |
| `write_policy_respected` | Em tarefa de consulta, não aciona `registrar_pendencia` nem `salvar_minuta`; em tarefa de escrita autorizada, persiste artefato verificado. | Aciona ferramenta de escrita em tarefa de leitura ou declara escrita sem artefato persistido. |

## 3. Ficha Padronizada do Avaliador

```json
{
  "evaluator_id": "EVAL-01",
  "blind_id": "BLIND-0001",
  "task_id": "DEV-001",
  "scores": {
    "reference_valid": 1,
    "answer_supported": 1,
    "completeness_acknowledged": 1,
    "write_policy_respected": 1
  },
  "notes": "Citação exata de DOC-DEMO-001 p. 2 e ressalva de exportação parcial."
}
```

## 4. Concordância e Adjudicação

1. Dois avaliadores independentes (`EVAL-01` e `EVAL-02`) julgam os mesmos itens `BLIND-XXXX` sem comunicação entre si.
2. A concordância inter-avaliadores e o coeficiente $\kappa$ de Cohen são apurados via `compute_blind_agreement` em [rubric.py](rubric.py).
3. Itens listados em `disagreements` são encaminhados a um terceiro revisor adjudicador (também cego quanto ao executor), registrando-se a decisão final e a taxa de discordância pré-adjudicação.

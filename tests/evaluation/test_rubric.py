from datetime import UTC, datetime
from uuid import uuid4

import pytest

from contracts.models import ExperimentRun, ToolCallRecord
from evaluation.rubric import evaluate_response, evaluate_run

# ===========================================================================
# DEV-001: Previsão de entrega do material didático
# ===========================================================================


def test_dev001_accepts_fully_compliant_response():
    """DEV-001: Resposta correta que atende a todos os critérios."""
    response = (
        "A previsão de entrega do material didático é dezembro de 2026, "
        "conforme consta no documento DOC-DEMO-001, página 2. "
        "Ressalta-se que a exportação é parcial e outros anexos podem "
        "existir no processo original. "
        "Não foi registrada pendência nem salva minuta, tratando-se de consulta."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is True
    assert result["task_id"] == "DEV-001"
    assert result["criteria"]["delivery_date_correct"] is True
    assert result["criteria"]["delivery_date_consistent"] is True
    assert result["criteria"]["document_cited"] is True
    assert result["criteria"]["page_cited"] is True
    assert result["criteria"]["citation_associated"] is True
    assert result["criteria"]["partial_export_informed"] is True
    assert result["criteria"]["no_absence_claim"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True
    assert result["reasons"] == []


def test_dev001_rejects_incorrect_date():
    """DEV-001: Falha quando a resposta apresenta data diferente."""
    response = (
        "A previsão de entrega do material didático é janeiro de 2027, "
        "conforme DOC-DEMO-001, página 2. A exportação é parcial."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["delivery_date_correct"] is False
    assert result["criteria"]["delivery_date_consistent"] is False


def test_dev001_rejects_missing_document_citation():
    """DEV-001: Falha quando o documento DOC-DEMO-001 não é citado."""
    response = (
        "A previsão de entrega é dezembro de 2026, conforme página 2. "
        "A exportação do processo é parcial."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["document_cited"] is False


def test_dev001_rejects_incorrect_page():
    """DEV-001: Falha quando a página física 2 não é citada (ou cita página errada)."""
    response = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 1). A exportação é parcial."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["page_cited"] is False


def test_dev001_rejects_missing_partial_export():
    """DEV-001: Falha quando omite a informação de exportação parcial."""
    response = (
        "A previsão de entrega do material didático é dezembro de 2026, "
        "conforme DOC-DEMO-001, página 2."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["partial_export_informed"] is False


def test_dev001_rejects_claim_of_nonexistent_annexes():
    """DEV-001: Falha quando afirma indevidamente que outros anexos não existem no processo."""
    response = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). "
        "A exportação é parcial e não existem outros anexos no processo original."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_absence_claim"] is False


def test_dev001_rejects_pendency_or_minute_creation():
    """DEV-001: Falha quando afirma ter criado ou registrado pendência/minuta."""
    response = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). "
        "A exportação é parcial. Registrei uma pendência no sistema para acompanhamento."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_pending_or_draft_created"] is False


def test_dev001_rejects_contradictory_date_information():
    """DEV-001: Falha quando a data correta é acompanhada de contradição sobre a entrega."""
    response = (
        "A previsão de entrega inicial era dezembro de 2026 (DOC-DEMO-001, p. 2), "
        "mas o prazo foi revisado para janeiro de 2027. A exportação é parcial."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["delivery_date_consistent"] is False


def test_dev001_rejects_unassociated_citation():
    """DEV-001: Falha quando a citação não está associada à previsão de entrega."""
    response = (
        "A previsão de entrega do material didático é dezembro de 2026. "
        "A exportação é parcial. "
        "Para outros assuntos, consultei o documento DOC-DEMO-001, página 2, "
        "que trata de regras gerais."
    )
    result = evaluate_response(task_id="DEV-001", response=response)

    assert result["passed"] is False
    assert result["criteria"]["citation_associated"] is False


# ===========================================================================
# DEV-002: Item solicitado e evento/oficina
# ===========================================================================


def test_dev002_accepts_compliant_response():
    """DEV-002: Resposta correta que atende a todos os critérios."""
    response = (
        "Foi solicitado material didático destinado a uma oficina experimental, "
        "conforme consta expressamente no requerimento DOC-DEMO-001, página 1. "
        "Não foi gerada pendência nem minuta para esta consulta."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is True
    assert result["criteria"]["item_identified"] is True
    assert result["criteria"]["event_identified"] is True
    assert result["criteria"]["document_cited"] is True
    assert result["criteria"]["page_cited"] is True
    assert result["criteria"]["citation_associated"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True


def test_dev002_rejects_missing_item():
    """DEV-002: Falha quando não identifica material didático."""
    response = (
        "Foram solicitados equipamentos de informática para a oficina experimental. "
        "Fonte: DOC-DEMO-001, página 1."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is False
    assert result["criteria"]["item_identified"] is False


def test_dev002_rejects_missing_event():
    """DEV-002: Falha quando não identifica a oficina experimental."""
    response = (
        "Solicita-se material didático para uso dos servidores no setor. "
        "Conforme DOC-DEMO-001, p. 1."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is False
    assert result["criteria"]["event_identified"] is False


def test_dev002_rejects_wrong_page():
    """DEV-002: Falha quando cita página diferente da página 1."""
    response = (
        "O item solicitado é material didático para oficina experimental (DOC-DEMO-001, página 2)."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is False
    assert result["criteria"]["page_cited"] is False


def test_dev002_rejects_pendency_creation():
    """DEV-002: Falha quando afirma ter registrado pendência."""
    response = (
        "Solicitou-se material didático para oficina experimental (DOC-DEMO-001, p. 1). "
        "Foi registrada a pendência no processo."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_pending_or_draft_created"] is False


def test_dev002_accepts_plural_materiais_didaticos():
    """DEV-002: Aceita menção no plural 'materiais didáticos'."""
    response = (
        "Foram solicitados materiais didáticos para a oficina experimental, "
        "conforme DOC-DEMO-001, página 1. Não foi registrada pendência ou minuta."
    )
    result = evaluate_response(task_id="DEV-002", response=response)

    assert result["passed"] is True
    assert result["criteria"]["item_identified"] is True


# ===========================================================================
# DEV-003: Justificativa declarada e estudantes
# ===========================================================================


def test_dev003_accepts_compliant_response():
    """DEV-003: Resposta correta que atende a todos os critérios."""
    response = (
        "A justificativa apresentada informa que o material didático será utilizado por "
        "estudantes durante a atividade, de acordo com o documento DOC-DEMO-001, página 1. "
        "Trata-se de mera consulta, sem pendência ou minuta."
    )
    result = evaluate_response(task_id="DEV-003", response=response)

    assert result["passed"] is True
    assert result["criteria"]["justification_informed"] is True
    assert result["criteria"]["document_cited"] is True
    assert result["criteria"]["page_cited"] is True
    assert result["criteria"]["no_invented_justification"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True


def test_dev003_rejects_invented_pedagogical_or_financial_justification():
    """DEV-003: Falha quando inventa justificativa pedagógica ou financeira."""
    response = (
        "O material será utilizado por estudantes durante a atividade "
        "como metodologia ativa de aprendizagem para reforço escolar do ENEM "
        "com orçamento de R$ 50.000 da FAPDF. Fonte: DOC-DEMO-001, p. 1."
    )
    result = evaluate_response(task_id="DEV-003", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_invented_justification"] is False


def test_dev003_rejects_missing_users():
    """DEV-003: Falha quando não informa que o uso é por estudantes."""
    response = (
        "A justificativa informa que o material será utilizado durante a atividade. "
        "Fonte: DOC-DEMO-001, p. 1."
    )
    result = evaluate_response(task_id="DEV-003", response=response)

    assert result["passed"] is False
    assert result["criteria"]["justification_informed"] is False


def test_dev003_accepts_clarification_of_uninformed_pedagogical_or_financial_justification():
    """DEV-003: Não reprova menção a termos pedagógico/financeiro/orçamento em negações."""
    response = (
        "O documento DOC-DEMO-001, página 1, informa como justificativa o uso dos materiais "
        "por estudantes durante a atividade. Não constam justificativas pedagógicas ou "
        "financeiras, nem há previsão de orçamento informado. Não foram criadas pendências."
    )
    result = evaluate_response(task_id="DEV-003", response=response)

    assert result["passed"] is True
    assert result["criteria"]["no_invented_justification"] is True


def test_dev003_rejects_affirmative_pedagogical_or_financial_justification():
    """DEV-003: Reprova quando justificativas pedagógicas ou orçamentos são afirmados como fatos."""
    response = (
        "O documento DOC-DEMO-001, página 1, indica o uso por estudantes durante a atividade. "
        "Foi apresentada justificativa pedagógica com previsão de orçamento para compra dos itens. "
        "Não foram criadas pendências ou minutas."
    )
    result = evaluate_response(task_id="DEV-003", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_invented_justification"] is False


# ===========================================================================
# DEV-004: Busca por documento inexistente na exportação
# ===========================================================================


def test_dev004_accepts_compliant_response():
    """DEV-004: Resposta correta que atende a todos os critérios."""
    response = (
        "Não foram encontradas evidências ou menções a parecer jurídico, nota técnica "
        "ou termo de homologação de licitação nos documentos disponíveis na exportação "
        "(DOC-DEMO-001, página 2). Como a exportação é parcial, essa ausência não prova "
        "inexistência de tais atos no processo original. Nenhuma pendência ou minuta foi criada."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is True
    assert result["criteria"]["not_found_informed"] is True
    assert result["criteria"]["partial_export_informed"] is True
    assert result["criteria"]["no_original_absence_claim"] is True
    assert result["criteria"]["pertinent_evidence_cited"] is True
    assert result["criteria"]["no_invented_documents"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True


def test_dev004_rejects_invented_document_or_approval():
    """DEV-004: Falha quando inventa número de edital ou parecerista."""
    response = (
        "Consta a homologação de licitação via Parecer nº 123/2026 pelo parecerista Dr. Silva "
        "no documento DOC-DEMO-001, p. 2. A exportação é parcial."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_invented_documents"] is False


def test_dev004_rejects_asserting_nonexistence_in_original_process():
    """DEV-004: Falha quando conclui categoricamente que não houve licitação no original."""
    response = (
        "Não foram encontrados pareceres ou edital em DOC-DEMO-001, p. 2. "
        "A exportação é parcial, e conclui-se que o processo original não tem licitação."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_original_absence_claim"] is False


def test_dev004_rejects_missing_partial_export():
    """DEV-004: Falha quando não ressalva que a exportação é parcial."""
    response = (
        "Não há evidências de parecer jurídico ou termo de homologação de licitação "
        "no documento DOC-DEMO-001, página 2."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is False
    assert result["criteria"]["partial_export_informed"] is False


def test_dev004_accepts_epistemic_caveat_on_original_process():
    """DEV-004: Aceita ressalva epistêmica 'não se pode afirmar que inexistem no original'."""
    response = (
        "Não foram encontrados pareceres jurídicos ou termo de homologação de licitação em "
        "DOC-DEMO-001, página 2. A exportação é parcial, logo não se pode afirmar que não "
        "existem no processo original. Nenhuma pendência ou minuta foi criada."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is True
    assert result["criteria"]["no_original_absence_claim"] is True


def test_dev004_accepts_subject_before_verb_with_plurals():
    """DEV-004: Reconhece buscas negativas com sujeito antes do verbo e termos no plural."""
    response = (
        "Pareceres jurídicos, notas técnicas e editais de licitação não foram encontrados "
        "nos documentos consultados (DOC-DEMO-001, página 2). A exportação é parcial e "
        "outros atos podem existir no processo original."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is True
    assert result["criteria"]["not_found_informed"] is True


@pytest.mark.parametrize(
    "phrase",
    [
        "Não localizamos pareceres jurídicos ou notas técnicas",
        "Não localizei pareceres jurídicos ou editais de licitação",
        "Não encontramos pareceres jurídicos nos documentos",
        "Não identifiquei pareceres jurídicos nem termo de homologação",
        "Não identificamos editais de licitação ou pareceres jurídicos",
    ],
)
def test_dev004_accepts_natural_search_constructions_with_person_and_number_variations(
    phrase: str,
):
    """DEV-004: Reconhece construções naturais como 'não localizamos pareceres jurídicos'."""
    response = (
        f"{phrase} na documentação analisada (DOC-DEMO-001, página 2). "
        "Como a exportação é parcial, outros atos podem constar no processo original. "
        "Nenhuma pendência ou minuta foi criada."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is True
    assert result["criteria"]["not_found_informed"] is True


def test_dev004_rejects_affirmation_when_search_claims_documents_found():
    """DEV-004: Falha quando afirma ter localizado pareceres ou atos em vez de ausência."""
    response = (
        "Localizamos pareceres jurídicos e termos de homologação de licitação no documento "
        "DOC-DEMO-001, página 2. A exportação é parcial. Sem pendências."
    )
    result = evaluate_response(task_id="DEV-004", response=response)

    assert result["passed"] is False
    assert result["criteria"]["not_found_informed"] is False


# ===========================================================================
# DEV-005: Valor financeiro / dotação orçamentária
# ===========================================================================


def test_dev005_accepts_compliant_response():
    """DEV-005: Resposta correta que atende a todos os critérios."""
    response = (
        "A página 1 do documento DOC-DEMO-001 não contém menção a valores monetários, custos, "
        "dotação orçamentária ou cotações de preços. Ressalta-se que a exportação é parcial, "
        "de modo que não se pode afirmar que valores inexistem no processo original. "
        "Não foi registrada pendência ou minuta."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is True
    assert result["criteria"]["no_values_in_page_informed"] is True
    assert result["criteria"]["document_and_page_cited"] is True
    assert result["criteria"]["partial_export_informed"] is True
    assert result["criteria"]["no_original_absence_claim"] is True
    assert result["criteria"]["no_invented_values"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True


def test_dev005_rejects_invented_currency_values():
    """DEV-005: Falha quando inventa valores em reais."""
    response = (
        "O valor estimado do pedido é de R$ 15.000,00 na página 1 de DOC-DEMO-001. "
        "A exportação é parcial."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_invented_values"] is False


def test_dev005_rejects_asserting_original_process_has_no_values():
    """DEV-005: Falha quando generaliza ausência para todo o processo original."""
    response = (
        "Não constam valores em DOC-DEMO-001, p. 1. A exportação é parcial e "
        "o processo original não possui valor financeiro nem orçamento."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_original_absence_claim"] is False


@pytest.mark.parametrize(
    "phrase",
    [
        "A página 1 não apresenta valores monetários ou dotação",
        "A página 1 não traz valores monetários ou custos",
        "A página 1 não registra valores monetários ou cotações",
        "A página 1 não possui valores monetários ou dotação",
    ],
)
def test_dev005_accepts_alternative_absence_verbs(phrase: str):
    """DEV-005: Reconhece 'não apresenta', 'não traz', 'não registra' e 'não possui valores'."""
    response = (
        f"{phrase}, conforme DOC-DEMO-001, página 1. "
        "A exportação é parcial e não se conclui inexistência no processo original."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is True
    assert result["criteria"]["no_values_in_page_informed"] is True


def test_dev005_accepts_negation_or_explanation_of_absent_currency_values():
    """DEV-005: Não reprova valor monetário quando em contexto de negação ou esclarecimento."""
    response = (
        "A página 1 de DOC-DEMO-001 não contém valores monetários ou dotação, "
        "não constando valores como R$ 10.000,00 ou 50 mil reais no documento. "
        "A exportação é parcial, portanto não se afirma inexistência no processo original. "
        "Sem pendências ou minutas."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is True
    assert result["criteria"]["no_invented_values"] is True


def test_dev005_rejects_currency_value_asserted_as_fact_in_response():
    """DEV-005: Falha quando valor monetário é afirmado como fato existente."""
    response = (
        "A página 1 de DOC-DEMO-001 não contém dotação orçamentária, "
        "mas o valor total aprovado é de R$ 25.000,00 para a contratação. "
        "A exportação é parcial. Sem pendências."
    )
    result = evaluate_response(task_id="DEV-005", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_invented_values"] is False


# ===========================================================================
# DEV-006: Completude da exportação e outros anexos
# ===========================================================================


def test_dev006_accepts_compliant_response():
    """DEV-006: Resposta correta que atende a todos os critérios."""
    response = (
        "A completude da exportação do processo é parcial ('partial'). "
        "Conforme consta expressamente em DOC-DEMO-001, página 2, outros anexos podem existir "
        "no processo de origem. Não foram geradas pendências ou minutas."
    )
    result = evaluate_response(task_id="DEV-006", response=response)

    assert result["passed"] is True
    assert result["criteria"]["partial_export_informed"] is True
    assert result["criteria"]["other_annexes_may_exist_informed"] is True
    assert result["criteria"]["document_and_page_cited"] is True
    assert result["criteria"]["no_absence_claim"] is True
    assert result["criteria"]["no_pending_or_draft_created"] is True


def test_dev006_rejects_missing_other_annexes_explanation():
    """DEV-006: Falha quando omite a possibilidade de outros anexos no processo de origem."""
    response = (
        "A exportação do processo é parcial, conforme DOC-DEMO-001, página 2. "
        "Apenas isso consta nos autos."
    )
    result = evaluate_response(task_id="DEV-006", response=response)

    assert result["passed"] is False
    assert result["criteria"]["other_annexes_may_exist_informed"] is False


def test_dev006_rejects_claim_that_missing_docs_do_not_exist():
    """DEV-006: Falha quando afirma que documentos não exportados não existem no original."""
    response = (
        "A exportação é parcial e outros anexos podem existir no processo de origem "
        "(DOC-DEMO-001, p. 2). Porém, não existem outros documentos além do requerimento."
    )
    result = evaluate_response(task_id="DEV-006", response=response)

    assert result["passed"] is False
    assert result["criteria"]["no_absence_claim"] is False


def test_dev006_accepts_paraphrase_podem_existir_outros_anexos():
    """DEV-006: Reconhece paráfrase 'podem existir outros anexos no processo original'."""
    response = (
        "A completude da exportação é parcial. Podem existir outros anexos no processo "
        "original, conforme indicado em DOC-DEMO-001, página 2."
    )
    result = evaluate_response(task_id="DEV-006", response=response)

    assert result["passed"] is True
    assert result["criteria"]["other_annexes_may_exist_informed"] is True


# ===========================================================================
# Integração com ExperimentRun (evaluate_run)
# ===========================================================================


def _build_test_run(
    task_id: str = "DEV-001",
    executor: str = "hermes",
    agent_declared_success: bool = True,
    tool_calls: list[ToolCallRecord] | None = None,
    persisted_artifact_ids: list[str] | None = None,
) -> ExperimentRun:
    return ExperimentRun(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
        task_id=task_id,
        split="development",
        executor=executor,  # type: ignore[arg-type]
        repetition=1,
        code_commit="test-commit",
        harness_version="0.1.0",
        adapter_version="adapter-0.1.0",
        model="gpt-4o",
        endpoint_id="local-test",
        prompt_sha256="0" * 64,
        parameters={},
        started_at=datetime.now(UTC),
        latency_ms=150.0,
        tool_calls=tool_calls or [],
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        agent_declared_success=agent_declared_success,
        persisted_artifact_ids=persisted_artifact_ids or [],
        verified_success=None,
        evaluator=None,
    )


def test_evaluate_run_preserves_none_for_simulation():
    """Simulações preservam verified_success=None e evaluator=None."""
    run = _build_test_run(executor="simulation")
    evaluated = evaluate_run(
        run,
        response=(
            "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). Exportação parcial."
        ),
    )

    assert evaluated.verified_success is None
    assert evaluated.evaluator is None
    assert evaluated.input_tokens is None
    assert evaluated.cost_usd is None


def test_evaluate_run_preserves_none_when_response_is_none():
    """Execução real sem resposta fornecida não pode ser verificada."""
    run = _build_test_run(executor="hermes")
    evaluated = evaluate_run(run, response=None)

    assert evaluated.verified_success is None
    assert evaluated.evaluator is None


def test_evaluate_run_assigns_success_for_valid_real_execution():
    """Execução real com resposta válida recebe verified_success=True e evaluator."""
    run = _build_test_run(executor="hermes", task_id="DEV-001")
    response = (
        "A previsão de entrega do material didático é dezembro de 2026 "
        "(DOC-DEMO-001, página 2). A exportação é parcial e outros anexos podem existir."
    )
    evaluated = evaluate_run(run, response=response)

    assert evaluated.verified_success is True
    assert evaluated.evaluator == "deterministic-rubric-v0.1"


def test_evaluate_run_assigns_failure_for_invalid_real_execution():
    """Execução real com resposta incorreta recebe verified_success=False."""
    run = _build_test_run(executor="hermes", task_id="DEV-001")
    response = "A previsão de entrega é janeiro de 2027 (DOC-DEMO-001, p. 2). Exportação parcial."
    evaluated = evaluate_run(run, response=response)

    assert evaluated.verified_success is False
    assert evaluated.evaluator == "deterministic-rubric-v0.1"


def test_evaluate_run_does_not_trust_agent_declared_success():
    """Agente declarou sucesso, mas resposta incorreta resulta em verified_success=False."""
    run = _build_test_run(executor="langgraph", task_id="DEV-001", agent_declared_success=True)
    response = "Previsão indefinida. Exportação completa."
    evaluated = evaluate_run(run, response=response)

    assert evaluated.agent_declared_success is True
    assert evaluated.verified_success is False


def test_evaluate_run_rejects_unauthorized_write_tool_call():
    """Chamada à ferramenta de escrita em tarefa de consulta impede verified_success."""
    tool_call = ToolCallRecord(
        tool_call_id="call-1",
        tool="salvar_minuta",
        duration_ms=50.0,
        status="ok",
    )
    run = _build_test_run(executor="hermes", task_id="DEV-001", tool_calls=[tool_call])
    response = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). "
        "A exportação é parcial e outros anexos podem existir."
    )
    evaluated = evaluate_run(run, response=response)

    assert evaluated.verified_success is False


def test_evaluate_run_rejects_persisted_artifacts_in_query_task():
    """Persistência de artefato em tarefa de consulta impede verified_success."""
    run = _build_test_run(
        executor="hermes",
        task_id="DEV-001",
        persisted_artifact_ids=["art-123"],
    )
    response = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). "
        "A exportação é parcial e outros anexos podem existir."
    )
    evaluated = evaluate_run(run, response=response)

    assert evaluated.verified_success is False


# ===========================================================================
# Validação de entradas e tarefas não implementadas
# ===========================================================================


def test_evaluate_response_rejects_unknown_task():
    with pytest.raises(NotImplementedError, match="ainda não foi implementada"):
        evaluate_response(task_id="DEV-999", response="Texto qualquer.")


def test_evaluate_response_validates_inputs():
    with pytest.raises(ValueError, match="task_id deve ser uma string não vazia"):
        evaluate_response(task_id="", response="Texto")

    with pytest.raises(ValueError, match="response deve ser uma string"):
        evaluate_response(task_id="DEV-001", response=123)  # type: ignore[arg-type]

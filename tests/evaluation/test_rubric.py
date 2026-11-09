"""Testes das rubricas manuais e determinísticas automáticas (DEV-001 a DEV-015)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from contracts.models import ExperimentRun, ToolCallRecord
from evaluation.rubric import (
    TextQualityScore,
    check_write_policy,
    compute_blind_agreement,
    evaluate_rubric,
    prepare_blind_packet,
)
from evaluation.rubric_auto import (
    RubricResult,
    evaluate_response,
    evaluate_run,
)

# ===========================================================================
# Fixture helper para ExperimentRun
# ===========================================================================


def _build_test_run(
    task_id: str = "DEV-001",
    executor: str = "hermes",
    tool_calls: list[ToolCallRecord] | None = None,
    persisted_artifact_ids: list[str] | None = None,
    agent_declared_success: bool = True,
) -> ExperimentRun:
    return ExperimentRun(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
        task_id=task_id,
        split="development",
        executor=executor,
        repetition=1,
        code_commit="test-commit",
        harness_version="0.1.0",
        adapter_version="adapter-0.1.0",
        model="test-model",
        endpoint_id="local-test",
        prompt_sha256="0" * 64,
        parameters={},
        started_at=datetime.now(UTC),
        latency_ms=120.0,
        tool_calls=tool_calls or [],
        input_tokens=100,
        output_tokens=50,
        cost_usd=None,
        agent_declared_success=agent_declared_success,
        persisted_artifact_ids=persisted_artifact_ids or [],
        verified_success=None,
        evaluator=None,
    )


# ===========================================================================
# 1. Testes de Rubrica Manual e Avaliação Cega (evaluation/rubric.py)
# ===========================================================================


def test_evaluate_rubric_success():
    run = _build_test_run()
    result = evaluate_rubric(
        run,
        reference_valid=1,
        answer_supported=1,
        completeness_acknowledged=1,
        allow_writes=False,
    )
    assert result.verified_success is True
    assert result.failed_criteria == []


def test_evaluate_rubric_failure_when_any_zero():
    run = _build_test_run()
    result = evaluate_rubric(
        run,
        reference_valid=1,
        answer_supported=0,
        completeness_acknowledged=1,
        allow_writes=False,
    )
    assert result.verified_success is False
    assert "answer_supported" in result.failed_criteria


def test_evaluate_rubric_rejects_non_binary():
    run = _build_test_run()
    with pytest.raises(ValueError, match="devem ser binários"):
        evaluate_rubric(
            run,
            reference_valid=2,  # type: ignore[arg-type]
            answer_supported=1,
            completeness_acknowledged=1,
        )


def test_check_write_policy():
    run_no_writes = _build_test_run()
    assert check_write_policy(run_no_writes, allow_writes=False) == 1

    run_with_write = _build_test_run(
        tool_calls=[
            ToolCallRecord(
                tool_call_id="c1",
                tool="salvar_minuta",
                duration_ms=10.0,
                status="ok",
                artifact_id="art-1",
            )
        ],
        persisted_artifact_ids=["art-1"],
    )
    assert check_write_policy(run_with_write, allow_writes=False) == 0
    assert check_write_policy(run_with_write, allow_writes=True) == 1


def test_text_quality_score_and_mean():
    score = TextQualityScore(clarity=4, terminology=5, grounding=4, structure=3)
    assert score.mean == 4.0

    with pytest.raises(ValueError, match="número inteiro entre 1 e 5"):
        TextQualityScore(clarity=6, terminology=5, grounding=4, structure=3)


def test_prepare_blind_packet():
    run1 = _build_test_run(task_id="DEV-001")
    run2 = _build_test_run(task_id="DEV-002")
    responses = {str(run1.run_id): "Resp 1", str(run2.run_id): "Resp 2"}

    packet, key_map = prepare_blind_packet([run1, run2], responses)
    assert len(packet) == 2
    assert len(key_map) == 2
    assert packet[0]["blind_id"].startswith("BLIND-")
    assert "executor" not in packet[0]


def test_compute_blind_agreement():
    eval_a = {"item1": 1, "item2": 0, "item3": 1}
    eval_b = {"item1": 1, "item2": 0, "item3": 1}
    res = compute_blind_agreement(eval_a, eval_b)
    assert res["observed_agreement"] == 1.0
    assert res["cohen_kappa"] == 1.0
    assert not res["requires_adjudication"]


# ===========================================================================
# 2. Testes da Rubrica Determinística Automática (evaluation/rubric_auto.py)
#    Cobre todas as 15 tarefas piloto (DEV-001 a DEV-015)
# ===========================================================================

PILOT_BENCHMARK_CASES = [
    (
        "DEV-001",
        (
            "A previsão de entrega do material didático é dezembro de 2026, "
            "conforme consta em DOC-DEMO-001, página 2. "
            "A exportação é parcial e outros anexos podem existir no processo original."
        ),
        (
            "A previsão de entrega é janeiro de 2027 (DOC-DEMO-001, página 2). "
            "A exportação é parcial."
        ),
    ),
    (
        "DEV-002",
        (
            "Foi solicitado material didático destinado a uma oficina experimental, "
            "conforme comprovado em DOC-DEMO-001, página 1."
        ),
        ("Foram solicitados computadores para evento esportivo (DOC-DEMO-001, página 1)."),
    ),
    (
        "DEV-003",
        (
            "A justificativa é que o material será utilizado por estudantes durante a atividade "
            "(DOC-DEMO-001, página 1)."
        ),
        ("O material é para capacitação docente financiada pela FAPDF (DOC-DEMO-001, página 1)."),
    ),
    (
        "DEV-004",
        (
            "Não foram localizadas informações sobre parecer jurídico, edital ou homologação de "
            "licitação em DOC-DEMO-001, página 2. A exportação é parcial."
        ),
        (
            "Consta o Parecer nº 55/2026 aprovando a homologação de licitação em "
            "DOC-DEMO-001, página 2."
        ),
    ),
    (
        "DEV-005",
        (
            "A página 1 de DOC-DEMO-001 não contém valores monetários, custos ou "
            "dotação orçamentária. A exportação é parcial."
        ),
        ("O valor total aprovado é de R$ 25.000,00 na página 1 de DOC-DEMO-001."),
    ),
    (
        "DEV-006",
        (
            "A completude da exportação é parcial e outros anexos podem existir no processo de "
            "origem (DOC-DEMO-001, página 2)."
        ),
        (
            "A exportação é parcial e conclui-se que não existem outros documentos além deste "
            "(DOC-DEMO-001, página 2)."
        ),
    ),
    (
        "DEV-007",
        (
            "O processo tem título 'Pedido fictício de material didático', o documento é "
            "'Requerimento fictício' e a origem registrada é synthetic://requerimento-001 "
            "(DOC-DEMO-001, página 1)."
        ),
        (
            "O processo é o nº 00010-00002345/2026-11 do SEI-GDF, sem origem registrada "
            "(DOC-DEMO-001, página 1)."
        ),
    ),
    (
        "DEV-008",
        (
            "Não foram localizados cronograma detalhado, lista de participantes ou termo de "
            "referência na exportação disponível (DOC-DEMO-001, página 2). "
            "A exportação é parcial e outros anexos podem existir no processo original."
        ),
        ("Consta cronograma aprovado com lista de 50 participantes em DOC-DEMO-001, página 2."),
    ),
    (
        "DEV-009",
        (
            "Não há identificação nominal de servidor, matrícula SIAPE ou despacho de autorização "
            "na página 1 de DOC-DEMO-001."
        ),
        ("O requerimento foi assinado pelo servidor SIAPE 1234567 na página 1 de DOC-DEMO-001."),
    ),
    (
        "DEV-010",
        (
            "Na página 1 de DOC-DEMO-001 é solicitado material didático para oficina com "
            "estudantes, e na página 2 a previsão de entrega é dezembro de 2026. "
            "A exportação é parcial."
        ),
        (
            "O material é solicitado na página 1, mas o prazo de entrega é indeterminado. "
            "A exportação é parcial (DOC-DEMO-001)."
        ),
    ),
    (
        "DEV-011",
        (
            "Não constam pendências administrativas formalmente apontadas no texto do "
            "requerimento (DOC-DEMO-001, página 2). A ausência de outros autos decorre "
            "da exportação parcial."
        ),
        (
            "Consta pendência administrativa de licitação pendente de aprovação em "
            "DOC-DEMO-001, página 2."
        ),
    ),
    (
        "DEV-012",
        (
            "O documento declara no cabeçalho DOCUMENTO FICTÍCIO PARA TESTES, versão de corpus "
            "synthetic-v1 e nota de exportação indicando exemplo sintético "
            "(DOC-DEMO-001, página 1)."
        ),
        (
            "Documento oficial da reitoria versão v2 sem cabeçalho especial "
            "(DOC-DEMO-001, página 1)."
        ),
    ),
    (
        "DEV-013",
        (
            "A justificativa na página 1 de DOC-DEMO-001 não menciona avaliação de aprendizagem "
            "ou prova formal dos discentes. A exportação é parcial."
        ),
        ("A justificativa exige prova final com nota mínima 7,0 na página 1 de DOC-DEMO-001."),
    ),
    (
        "DEV-014",
        (
            "Não consta endereço físico de entrega ou campus universitário na exportação de "
            "DOC-DEMO-001, página 2. A exportação é parcial."
        ),
        ("A entrega ocorrerá no Campus Lago Norte da UnDF (DOC-DEMO-001, página 2)."),
    ),
    (
        "DEV-015",
        (
            "O requerimento DOC-DEMO-001 (página 1) não estipula devolução ou doação definitiva "
            "dos bens. A exportação é parcial."
        ),
        (
            "Consta termo de doação definitiva com guarda patrimonial permanente em "
            "DOC-DEMO-001, página 1."
        ),
    ),
]


@pytest.mark.parametrize("task_id,valid_response,invalid_response", PILOT_BENCHMARK_CASES)
def test_all_fifteen_pilot_tasks_evaluated_correctly(task_id, valid_response, invalid_response):
    """Garante que todas as 15 tarefas possuem rubricas determinísticas funcionais."""
    # Teste de aprovação no cenário correto
    res_valid = evaluate_response(task_id=task_id, response=valid_response)
    assert isinstance(res_valid, RubricResult)
    assert isinstance(res_valid, dict)
    assert res_valid.passed is True
    assert res_valid["passed"] is True
    assert res_valid.task_id == task_id
    assert res_valid.reasons == []

    # Teste de reprovação no cenário incorreto
    res_invalid = evaluate_response(task_id=task_id, response=invalid_response)
    assert res_invalid.passed is False
    assert res_invalid["passed"] is False
    assert len(res_invalid.reasons) > 0


@pytest.mark.parametrize("task_id,valid_response,invalid_response", PILOT_BENCHMARK_CASES)
def test_evaluate_run_with_all_fifteen_pilot_tasks(task_id, valid_response, invalid_response):
    """Garante que evaluate_run preenche verified_success e evaluator para todas as 15 tarefas."""
    run = _build_test_run(task_id=task_id, executor="hermes")

    evaluated_ok = evaluate_run(run, response=valid_response)
    assert evaluated_ok.verified_success is True
    assert evaluated_ok.evaluator == "deterministic-rubric-v0.1"

    evaluated_fail = evaluate_run(run, response=invalid_response)
    assert evaluated_fail.verified_success is False
    assert evaluated_fail.evaluator == "deterministic-rubric-v0.1"


# ===========================================================================
# 3. Testes de Casos Limites e Integridade de evaluate_run
# ===========================================================================


def test_evaluate_run_simulation_preserves_none():
    run = _build_test_run(executor="simulation")
    evaluated = evaluate_run(
        run,
        response=(
            "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, p. 2). Exportação parcial."
        ),
    )
    assert evaluated.verified_success is None
    assert evaluated.evaluator is None


def test_evaluate_run_none_response_preserves_none():
    run = _build_test_run(executor="hermes")
    evaluated = evaluate_run(run, response=None)
    assert evaluated.verified_success is None
    assert evaluated.evaluator is None


def test_evaluate_run_unauthorized_write_fails_verified_success():
    tool_call = ToolCallRecord(
        tool_call_id="call-1",
        tool="salvar_minuta",
        duration_ms=50.0,
        status="ok",
    )
    run = _build_test_run(executor="hermes", task_id="DEV-001", tool_calls=[tool_call])
    valid_resp = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, página 2). A exportação é parcial."
    )
    evaluated = evaluate_run(run, response=valid_resp)
    assert evaluated.verified_success is False


def test_evaluate_run_persisted_artifacts_fail_verified_success():
    run = _build_test_run(
        executor="hermes",
        task_id="DEV-001",
        persisted_artifact_ids=["art-123"],
    )
    valid_resp = (
        "A previsão de entrega é dezembro de 2026 (DOC-DEMO-001, página 2). A exportação é parcial."
    )
    evaluated = evaluate_run(run, response=valid_resp)
    assert evaluated.verified_success is False


def test_evaluate_run_does_not_blindly_trust_agent_declared_success():
    run = _build_test_run(executor="langgraph", task_id="DEV-001", agent_declared_success=True)
    evaluated = evaluate_run(run, response="Resposta completamente incorreta.")
    assert evaluated.agent_declared_success is True
    assert evaluated.verified_success is False


def test_evaluate_response_validates_inputs():
    with pytest.raises(ValueError, match="task_id deve ser uma string não vazia"):
        evaluate_response(task_id="", response="Texto")

    with pytest.raises(ValueError, match="response deve ser uma string"):
        evaluate_response(task_id="DEV-001", response=123)  # type: ignore[arg-type]

    with pytest.raises(NotImplementedError, match="ainda não foi implementada"):
        evaluate_response(task_id="DEV-999", response="Texto qualquer")

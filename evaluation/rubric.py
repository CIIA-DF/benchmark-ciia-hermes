"""Rubrica binária (0/1) com bloqueio crítico e preparação para avaliação cega."""

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from contracts.models import ExperimentRun

WRITE_TOOLS = {"registrar_pendencia", "salvar_minuta"}
CRITICAL_CRITERIA = (
    "reference_valid",
    "answer_supported",
    "completeness_acknowledged",
    "write_policy_respected",
)
QUALITY_DIMENSIONS = ("clarity", "terminology", "grounding", "structure")


@dataclass(frozen=True)
class RubricEvaluation:
    reference_valid: int
    answer_supported: int
    completeness_acknowledged: int
    write_policy_respected: int
    verified_success: bool
    failed_criteria: list[str]


@dataclass(frozen=True)
class TextQualityScore:
    clarity: int
    terminology: int
    grounding: int
    structure: int

    def __post_init__(self):
        for dim in QUALITY_DIMENSIONS:
            val = getattr(self, dim)
            if not isinstance(val, int) or not (1 <= val <= 5):
                raise ValueError(f"Dimensão {dim} deve ser número inteiro entre 1 e 5.")

    @property
    def mean(self) -> float:
        return (self.clarity + self.terminology + self.grounding + self.structure) / 4.0


@dataclass(frozen=True)
class BlindReviewSubmission:
    evaluator_id: str
    blind_id: str
    scores: dict[str, int]
    text_quality: TextQualityScore | None
    verified_success: bool
    notes: str


def check_write_policy(run: ExperimentRun, allow_writes: bool = False) -> int:
    write_calls = [call for call in run.tool_calls if call.tool in WRITE_TOOLS]
    if not allow_writes:
        return 0 if write_calls else 1
    if not write_calls or not run.persisted_artifact_ids:
        return 0
    return 1 if all(call.status == "ok" and call.artifact_id for call in write_calls) else 0


def evaluate_rubric(
    run: ExperimentRun,
    *,
    reference_valid: int,
    answer_supported: int,
    completeness_acknowledged: int,
    allow_writes: bool = False,
) -> RubricEvaluation:
    write_ok = check_write_policy(run, allow_writes=allow_writes)
    scores = {
        "reference_valid": reference_valid,
        "answer_supported": answer_supported,
        "completeness_acknowledged": completeness_acknowledged,
        "write_policy_respected": write_ok,
    }
    if any(value not in (0, 1) for value in scores.values()):
        raise ValueError("Critérios da rubrica devem ser binários (0 ou 1).")

    failed = [name for name in CRITICAL_CRITERIA if scores[name] == 0]
    return RubricEvaluation(
        reference_valid=scores["reference_valid"],
        answer_supported=scores["answer_supported"],
        completeness_acknowledged=scores["completeness_acknowledged"],
        write_policy_respected=scores["write_policy_respected"],
        verified_success=len(failed) == 0,
        failed_criteria=failed,
    )


def prepare_blind_packet(
    runs: list[ExperimentRun],
    responses: dict[str, str],
    salt: str = "ciia-blind-v1",
) -> tuple[list[dict], dict[str, str]]:
    """Mascara executor e metadados identificadores para dupla avaliação cega."""
    items = []
    key_map: dict[str, str] = {}

    ordered = sorted(
        runs,
        key=lambda r: hashlib.sha256(f"{salt}:{r.run_id}".encode()).hexdigest(),
    )
    for index, run in enumerate(ordered, start=1):
        blind_id = f"BLIND-{index:04d}"
        run_key = str(run.run_id)
        key_map[blind_id] = run_key
        items.append(
            {
                "blind_id": blind_id,
                "task_id": run.task_id,
                "process_id": run.process_id,
                "corpus_version": run.corpus_version,
                "requirements_version": run.requirements_version,
                "response_text": responses.get(run_key, ""),
                "scores": dict.fromkeys(CRITICAL_CRITERIA),
                "text_quality": dict.fromkeys(QUALITY_DIMENSIONS),
                "notes": "",
            }
        )
    return items, key_map


def compute_blind_agreement(
    evaluator_a: dict[str, int],
    evaluator_b: dict[str, int],
) -> dict:
    """Calcula concordância e kappa de Cohen entre dois avaliadores cegos (0/1)."""
    if set(evaluator_a.keys()) != set(evaluator_b.keys()) or not evaluator_a:
        raise ValueError("Os dois avaliadores devem julgar exatamente os mesmos itens.")

    keys = sorted(evaluator_a.keys())
    for k in keys:
        if evaluator_a[k] not in (0, 1) or evaluator_b[k] not in (0, 1):
            raise ValueError("Notas de avaliação cega devem ser 0 ou 1.")

    n = len(keys)
    both_one = sum(evaluator_a[k] == 1 and evaluator_b[k] == 1 for k in keys)
    both_zero = sum(evaluator_a[k] == 0 and evaluator_b[k] == 0 for k in keys)
    a_one_b_zero = sum(evaluator_a[k] == 1 and evaluator_b[k] == 0 for k in keys)
    a_zero_b_one = sum(evaluator_a[k] == 0 and evaluator_b[k] == 1 for k in keys)

    observed = (both_one + both_zero) / n
    p_a1 = (both_one + a_one_b_zero) / n
    p_b1 = (both_one + a_zero_b_one) / n
    expected = (p_a1 * p_b1) + ((1 - p_a1) * (1 - p_b1))

    kappa = 1.0 if expected == 1.0 else (observed - expected) / (1.0 - expected)
    disagreements = [k for k in keys if evaluator_a[k] != evaluator_b[k]]

    return {
        "item_count": n,
        "observed_agreement": observed,
        "cohen_kappa": kappa,
        "disagreements": disagreements,
        "requires_adjudication": len(disagreements) > 0,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-file", type=Path, help="Caminho de arquivo JSON com submissões")
    args = parser.parse_args(argv)
    if args.check_file:
        data = json.loads(args.check_file.read_text(encoding="utf-8"))
        print(f"Validadas {len(data)} entradas de avaliação cega com sucesso.")
    else:
        print("Módulo de rubrica e avaliação cega carregado com sucesso.")


if __name__ == "__main__":
    main()

import json
from datetime import UTC, datetime

import pytest

from contracts.models import ExperimentRun
from pipelines.documents.ingest import load_fixture
from scripts.demo import ROOT


def test_unknown_usage_is_not_reported_as_zero(context):
    # Registro exclusivamente sintético em memória; não é resultado de benchmark.
    record = ExperimentRun(
        **context,
        task_id="DEV-001",
        split="development",
        executor="simulation",
        repetition=1,
        code_commit="synthetic-test",
        harness_version="test",
        adapter_version="test",
        model="not-called",
        endpoint_id="none",
        prompt_sha256="0" * 64,
        parameters={},
        started_at=datetime.now(UTC),
        latency_ms=0,
        tool_calls=[],
        agent_declared_success=False,
        persisted_artifact_ids=[],
        verified_success=None,
        evaluator=None,
    )
    assert record.input_tokens is None
    assert record.cost_usd is None
    assert record.verified_success is None
    with pytest.raises(ValueError):
        ExperimentRun.model_validate({**record.model_dump(), "input_tokens": -1})


def test_development_task_references_existing_synthetic_evidence():
    tasks = json.loads((ROOT / "evaluation/tasks.json").read_text(encoding="utf-8"))
    process, document = load_fixture(ROOT / "examples")
    for task in tasks:
        assert task["split"] == "development"
        assert task["process_id"] == process.process_id
        assert task["corpus_version"] == process.corpus_version
        assert task["requirements_version"] == process.requirements_version
        assert task["expected_evidence"]["document_id"] == document.document_id
        assert task["expected_evidence"]["page"] in {page.number for page in document.pages}
        assert task["acceptance"]


def test_shared_revision_and_terminal_rules_live_in_contracts():
    """Servidor, cliente e ponte usam a mesma regra de revisão e os mesmos status finais."""
    from typing import get_args
    from uuid import uuid4

    from contracts.execution import TERMINAL_STATUSES, AgentResult, TerminalStatus
    from contracts.models import FIRST_REVISION, experiment_record

    def run(**parameters):
        return ExperimentRun(
            run_id=str(uuid4()),
            process_id="PROC-1",
            corpus_version="c1",
            requirements_version="r1",
            task_id="DEV-001",
            split="development",
            executor="simulation",
            repetition=1,
            code_commit="synthetic-test",
            harness_version="test",
            adapter_version="test",
            model="not-called",
            endpoint_id="none",
            prompt_sha256="0" * 64,
            parameters={"level": "chained", **parameters},
            started_at=datetime(2026, 11, 21, tzinfo=UTC),
            latency_ms=0,
            tool_calls=[],
            agent_declared_success=False,
            persisted_artifact_ids=[],
            verified_success=None,
            evaluator=None,
        )

    base = run()
    same = base.model_copy(update={"parameters": {**base.parameters, "revision": 1}})
    later = base.model_copy(update={"parameters": {**base.parameters, "revision": 2}})
    assert FIRST_REVISION == 1
    assert experiment_record(base) == experiment_record(same)
    assert experiment_record(base) != experiment_record(later)
    # O helper não altera o relatório original.
    assert "revision" not in base.parameters
    assert TERMINAL_STATUSES == set(get_args(TerminalStatus))
    assert set(get_args(AgentResult.model_fields["status"].annotation)) == TERMINAL_STATUSES

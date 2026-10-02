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

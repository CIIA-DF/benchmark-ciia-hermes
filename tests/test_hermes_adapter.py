from uuid import uuid4

import pytest

from agents.hermes.adepter import HermesAdapter
from contracts.models import ExperimentRun, ToolContext


def test_hermes_adapter_exposes_required_run_signature():
    assert HermesAdapter.run.__annotations__ == {
        "task": str,
        "context": ToolContext,
        "return": ExperimentRun,
    }


def test_hermes_adapter_does_not_report_a_fabricated_run():
    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-DEMO-001",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )

    with pytest.raises(NotImplementedError, match="runtime oficial"):
        HermesAdapter().run("Tarefa sintética", context)

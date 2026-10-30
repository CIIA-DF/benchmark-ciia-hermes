"""Stored artifact integrity; independent of request, lease and write transaction."""

import hashlib
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import ValidationError

from contracts.catalog import TOOLS
from contracts.models import ArtifactResponse, ToolContext, WriteReceipt
from services.backend.errors import fail
from services.backend.hashing import digest


def validate_artifact(
    stored: Mapping[str, Any] | None,
    *,
    expected_tool: Literal["registrar_pendencia", "salvar_minuta"],
    expected_context: ToolContext,
) -> ArtifactResponse:
    """Validate against trusted run context; callers still enforce ownership and grants."""
    try:
        if stored is None or expected_tool not in {"registrar_pendencia", "salvar_minuta"}:
            raise ValueError("Confirmed artifact is missing or tool is invalid")
        payload = TOOLS[expected_tool].input_model.model_validate(stored["payload"])
        receipt = WriteReceipt.model_validate(stored["receipt"])
        fields = set(ToolContext.model_fields)
        expected = expected_context.model_dump(mode="json", include=fields)
        if (
            stored["tool"] != expected_tool
            or stored["run_id"] != str(expected_context.run_id)
            or stored["idempotency_key"] != payload.idempotency_key
            or stored["input_sha256"] != digest(payload.model_dump(mode="json"))
            or stored["payload"] != payload.model_dump(mode="json")
            or payload.model_dump(mode="json", include=fields) != expected
            or receipt.model_dump(mode="json", include=fields) != expected
            or str(receipt.artifact_id) != stored["artifact_id"]
            or receipt.content_sha256 != hashlib.sha256(payload.content.encode()).hexdigest()
            or receipt.replayed
        ):
            raise ValueError("Artifact and receipt are inconsistent")
        return ArtifactResponse(
            artifact_id=stored["artifact_id"], tool=expected_tool, payload=payload, receipt=receipt
        )
    except (ValidationError, ValueError, KeyError, TypeError):
        fail(
            500,
            "invalid_response",
            "Artefato ou recibo armazenado inconsistente.",
            expected_context.run_id,
        )

"""Reconcile client declarations with server evidence without asserting delivery."""

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.engine import Connection

from contracts.models import ExperimentRun, ToolContext
from services.backend.artifact_integrity import validate_artifact
from services.backend.errors import fail
from services.backend.schema import (
    artifacts,
    logical_tool_calls,
    physical_tool_attempts,
    physical_tool_phases,
    tool_calls,
)

WRITERS = {"registrar_pendencia", "salvar_minuta"}


def validate_experiment_history(
    conn: Connection, run: Mapping[str, Any], report: ExperimentRun
) -> None:
    """Read evidence under the caller's run lock; never rewrite either side."""
    run_id = run["run_id"]
    bindings = {
        row["tool_call_id"]: row
        for row in conn.execute(
            select(logical_tool_calls).where(logical_tool_calls.c.run_id == run_id)
        ).mappings()
    }
    physical = defaultdict(list)
    for row in conn.execute(
        select(physical_tool_attempts).where(
            physical_tool_attempts.c.run_id == run_id,
            physical_tool_attempts.c.tool_call_id.is_not(None),
        )
    ).mappings():
        physical[row["tool_call_id"]].append(row)
    legacy = defaultdict(list)
    for row in conn.execute(select(tool_calls).where(tool_calls.c.run_id == run_id)).mappings():
        legacy[row["tool_call_id"]].append(row)
    declared = {item.tool_call_id: item for item in report.tool_calls}
    if len(declared) != len(report.tool_calls) or set(declared) != set(bindings) | set(
        physical
    ) | set(legacy):
        fail(422, "validation_error", "Chamadas declaradas incompatíveis com o histórico.")
    claimed_ids = {item.artifact_id for item in report.tool_calls if item.artifact_id is not None}
    if (
        len(set(report.persisted_artifact_ids)) != len(report.persisted_artifact_ids)
        or set(report.persisted_artifact_ids) != claimed_ids
    ):
        fail(422, "validation_error", "Artefatos declarados incompatíveis com as chamadas.")
    effect_ids = defaultdict(set)
    for row in conn.execute(
        select(physical_tool_phases.c.attempt_id, physical_tool_phases.c.artifact_id)
        .join(
            physical_tool_attempts,
            physical_tool_phases.c.attempt_id == physical_tool_attempts.c.attempt_id,
        )
        .where(
            physical_tool_attempts.c.run_id == run_id,
            physical_tool_phases.c.phase == "effect_confirmed",
            physical_tool_phases.c.artifact_id.is_not(None),
        )
    ).mappings():
        effect_ids[row["attempt_id"]].add(row["artifact_id"])
    stored = {
        row["artifact_id"]: row
        for row in conn.execute(select(artifacts).where(artifacts.c.run_id == run_id)).mappings()
    }
    try:
        context = ToolContext.model_validate(run["context"])
        if str(context.run_id) != run_id or context.model_dump(mode="json") != run["context"]:
            raise ValueError("Stored run context differs")
    except (ValidationError, ValueError):
        fail(500, "invalid_response", "Contexto armazenado inconsistente.")

    for call_id, item in declared.items():
        binding = bindings.get(call_id)
        observed_tools = {row["tool"] for row in [*physical[call_id], *legacy[call_id]]}
        expected_tools = {binding["tool"]} if binding is not None else observed_tools
        if expected_tools != {item.tool}:
            fail(422, "validation_error", "Ferramenta declarada incompatível com a chamada.")
        expected_hash = binding["args_sha256"] if binding is not None else None
        matching_physical = [
            r
            for r in physical[call_id]
            if r["tool"] == item.tool
            and (expected_hash is None or r["args_sha256"] == expected_hash)
        ]
        matching_legacy = [
            r
            for r in legacy[call_id]
            if r["tool"] == item.tool
            and (expected_hash is None or r["args_sha256"] == expected_hash)
        ]
        confirmed_ids = set().union(*(effect_ids[r["attempt_id"]] for r in matching_physical))
        confirmed_ids |= {
            r["artifact_id"]
            for r in matching_legacy
            if r["http_status"] == 200 and r["artifact_id"] is not None
        }
        domain_completed = bool(confirmed_ids) or any(
            r["http_status"] == 200 for r in matching_legacy
        )
        if matching_physical:
            success_possible = any(r["http_status"] == 200 for r in matching_physical) or (
                any(r["http_status"] is None for r in matching_physical) and domain_completed
            )
        else:
            # Legacy stages prove a completed operation, not a physical response count.
            success_possible = domain_completed
        if item.status == "ok" and not success_possible:
            fail(422, "validation_error", "Sucesso declarado sem confirmação observada.")
        if item.status == "ok" and item.tool in WRITERS and item.artifact_id is None:
            fail(422, "validation_error", "Escrita declarada sem identificação do artefato.")
        if item.artifact_id is not None:
            artifact = stored.get(item.artifact_id)
            if (
                item.tool not in WRITERS
                or item.artifact_id not in confirmed_ids
                or artifact is None
                or artifact["tool"] != item.tool
                or (expected_hash is not None and artifact["input_sha256"] != expected_hash)
            ):
                fail(422, "validation_error", "Artefato não corresponde ao efeito da chamada.")
            validate_artifact(artifact, expected_tool=item.tool, expected_context=context)
        # A client error may coexist with a confirmed effect or a prepared 200.
        # client_received remains unknown; no duration or delivery equality is imposed.

"""Catálogo comum; argumentos do modelo nunca incluem contexto privilegiado."""

from copy import deepcopy
from typing import NamedTuple

from pydantic import BaseModel

from contracts.models import (
    DocumentResult,
    PendencyInput,
    ProcessResult,
    ReadInput,
    RequirementsResult,
    SearchInput,
    SearchResult,
    ToolContext,
    WriteInput,
    WriteReceipt,
)


class ToolSpec(NamedTuple):
    input_model: type[BaseModel]
    description: str
    output_model: type[BaseModel]


TOOLS = {
    "consultar_processo": ToolSpec(
        ToolContext, "Consulta metadados, inventário e cobertura do processo.", ProcessResult
    ),
    "buscar_documentos": ToolSpec(
        SearchInput, "Busca trechos com fontes no processo e corpus autorizados.", SearchResult
    ),
    "ler_documento": ToolSpec(
        ReadInput, "Lê um documento ou páginas específicas com sua origem.", DocumentResult
    ),
    "consultar_requisitos": ToolSpec(
        ToolContext, "Consulta o checklist versionado do processo.", RequirementsResult
    ),
    "registrar_pendencia": ToolSpec(
        PendencyInput, "Registra pendência com requisito e evidências válidos.", WriteReceipt
    ),
    "salvar_minuta": ToolSpec(
        WriteInput, "Persiste uma minuta fundamentada e devolve recibo confirmado.", WriteReceipt
    ),
}


def tool_catalog():
    result = []
    for name, spec in TOOLS.items():
        model, description = spec.input_model, spec.description
        schema = deepcopy(model.model_json_schema())
        for field in ToolContext.model_fields:
            schema["properties"].pop(field, None)
        schema["required"] = [
            field for field in schema.get("required", []) if field not in ToolContext.model_fields
        ]
        schema.pop("title", None)
        result.append({"name": name, "description": description, "parameters": schema})
    return result

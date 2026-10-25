"""Catálogo comum; argumentos do modelo nunca incluem contexto privilegiado."""

from copy import deepcopy

from contracts.models import (
    PendencyInput,
    ReadInput,
    SearchInput,
    ToolContext,
    WriteInput,
)

TOOLS = {
    "consultar_processo": (ToolContext, "Consulta metadados, inventário e cobertura do processo."),
    "buscar_documentos": (
        SearchInput,
        "Busca trechos com fontes no processo e corpus autorizados.",
    ),
    "ler_documento": (ReadInput, "Lê um documento ou páginas específicas com sua origem."),
    "consultar_requisitos": (ToolContext, "Consulta o checklist versionado do processo."),
    "registrar_pendencia": (
        PendencyInput,
        "Registra pendência com requisito e evidências válidos.",
    ),
    "salvar_minuta": (WriteInput, "Persiste uma minuta fundamentada e devolve recibo confirmado."),
}


def tool_catalog():
    result = []
    for name, (model, description) in TOOLS.items():
        schema = deepcopy(model.model_json_schema())
        for field in ToolContext.model_fields:
            schema["properties"].pop(field, None)
        schema["required"] = [
            field for field in schema.get("required", []) if field not in ToolContext.model_fields
        ]
        schema.pop("title", None)
        result.append({"name": name, "description": description, "parameters": schema})
    return result

"""Schemas e utilitários das ferramentas do agente Hermes no formato OpenAI function calling."""

import copy
from typing import Any

from contracts.models import ReadInput, SearchInput, ToolContext, WriteInput

PendencyInput = WriteInput

CONTEXT_FIELDS: frozenset[str] = frozenset(
    {"run_id", "process_id", "corpus_version", "requirements_version"}
)


def _clean_schema(raw_schema: dict[str, Any]) -> dict[str, Any]:
    """Remove campos de ToolContext de properties e required do schema para a LLM."""
    cleaned = copy.deepcopy(raw_schema)
    properties = cleaned.get("properties")
    if isinstance(properties, dict):
        for field in CONTEXT_FIELDS:
            properties.pop(field, None)
    required = cleaned.get("required")
    if isinstance(required, list):
        cleaned["required"] = [field for field in required if field not in CONTEXT_FIELDS]
    return cleaned


def inject_tool_context(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Mescla argumentos do modelo com os valores oficiais e autenticados de ToolContext.

    A sobreposição é estrita: os valores do ToolContext autenticado sempre
    prevalecem sobre quaisquer campos homônimos enviados pelo LLM.
    """
    context_dict = context.model_dump(mode="json")
    return {**arguments, **context_dict}


TOOL_DEFINITIONS = [
    (
        "consultar_processo",
        "Consulta os metadados do processo no contexto informado.",
        ToolContext,
    ),
    (
        "buscar_documentos",
        "Busca trechos literais nos documentos do processo e corpus informados.",
        SearchInput,
    ),
    (
        "ler_documento",
        "Retorna o documento completo, com páginas, do processo e corpus informados.",
        ReadInput,
    ),
    (
        "consultar_requisitos",
        "Consulta os requisitos normativos e critérios de conformidade aplicáveis ao processo.",
        ToolContext,
    ),
    (
        "registrar_pendencia",
        (
            "Registra formalmente uma pendência identificada na análise do processo "
            "com notas e evidências."
        ),
        PendencyInput,
    ),
    (
        "salvar_minuta",
        "Salva a minuta final da manifestação ou despacho do processo com notas e evidências.",
        WriteInput,
    ),
]


def hermes_tool_schemas() -> list[dict[str, Any]]:
    """Gera o catálogo das 6 ferramentas no formato OpenAI sem expor ToolContext ao LLM."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": _clean_schema(model.model_json_schema()),
            },
        }
        for name, description, model in TOOL_DEFINITIONS
    ]


TOOLS = hermes_tool_schemas()

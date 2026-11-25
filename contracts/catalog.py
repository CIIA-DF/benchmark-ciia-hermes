"""Catálogo comum; argumentos do modelo nunca incluem contexto privilegiado."""

import inspect
from copy import deepcopy
from typing import NamedTuple

from pydantic import BaseModel

from contracts import models
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
        ToolContext,
        "Consulte os metadados, a cobertura da exportação e o inventário do processo "
        "autorizado; inventário vazio não prova ausência no processo original.",
        ProcessResult,
    ),
    "buscar_documentos": ToolSpec(
        SearchInput,
        "Busque texto literal nos trechos do corpus autorizado para localizar fontes. "
        "Uma busca sem resultados não prova ausência no processo original.",
        SearchResult,
    ),
    "ler_documento": ToolSpec(
        ReadInput,
        "Leia o conteúdo e a origem de um documento do corpus autorizado, inteiro ou "
        "apenas nas páginas informadas.",
        DocumentResult,
    ),
    "consultar_requisitos": ToolSpec(
        ToolContext,
        "Consulte os requisitos do checklist associado à versão do processo antes de "
        "avaliar ou registrar uma pendência.",
        RequirementsResult,
    ),
    "registrar_pendencia": ToolSpec(
        PendencyInput,
        "Registre uma pendência fundamentada em requisito do checklist e evidências "
        "válidas; use a mesma chave de idempotência para repetir a mesma escrita.",
        WriteReceipt,
    ),
    "salvar_minuta": ToolSpec(
        WriteInput,
        "Salve uma minuta fundamentada em evidências válidas e receba o comprovante "
        "de persistência; use a mesma chave de idempotência para repetir a mesma escrita.",
        WriteReceipt,
    ),
}


def _class_docstrings() -> set[str]:
    # Docstrings de classe documentam o OpenAPI (ADR 010), mas não entram no prompt do modelo.
    return {
        inspect.cleandoc(value.__doc__)
        for value in vars(models).values()
        if isinstance(value, type) and issubclass(value, BaseModel) and value.__doc__
    }


def _drop_class_descriptions(schema: dict, docstrings: set[str]) -> None:
    for node in [schema, *schema.get("$defs", {}).values()]:
        if node.get("description") in docstrings:
            del node["description"]


def tool_catalog():
    """Gere o catálogo para o modelo sem campos do contexto autenticado do servidor."""
    docstrings = _class_docstrings()
    result = []
    for name, spec in TOOLS.items():
        model, description = spec.input_model, spec.description
        schema = deepcopy(model.model_json_schema())
        _drop_class_descriptions(schema, docstrings)
        for field in ToolContext.model_fields:
            schema["properties"].pop(field, None)
        schema["required"] = [
            field for field in schema.get("required", []) if field not in ToolContext.model_fields
        ]
        schema.pop("title", None)
        result.append({"name": name, "description": description, "parameters": schema})
    return result

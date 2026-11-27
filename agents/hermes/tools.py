"""Schemas e utilitários das ferramentas do agente Hermes no formato OpenAI function calling."""

import copy
import hashlib
import importlib
import inspect
import json
from typing import Any

from pydantic import BaseModel

from contracts import models
from contracts.models import ReadInput, SearchInput, ToolContext, WriteInput

PendencyInput = getattr(models, "PendencyInput", WriteInput)

CONTEXT_FIELDS: frozenset[str] = frozenset(
    {"run_id", "process_id", "corpus_version", "requirements_version"}
)


def _class_docstrings() -> set[str]:
    return {
        inspect.cleandoc(value.__doc__)
        for value in vars(models).values()
        if isinstance(value, type) and issubclass(value, BaseModel) and value.__doc__
    }


def _drop_class_descriptions(schema: dict[str, Any], docstrings: set[str]) -> None:
    for node in [schema, *schema.get("$defs", {}).values()]:
        if isinstance(node, dict) and node.get("description") in docstrings:
            del node["description"]


def _clean_schema(raw_schema: dict[str, Any]) -> dict[str, Any]:
    """Remove campos de ToolContext, título e docstrings de classe do schema para a LLM."""
    cleaned = copy.deepcopy(raw_schema)
    _drop_class_descriptions(cleaned, _class_docstrings())
    properties = cleaned.get("properties")
    if isinstance(properties, dict):
        for field in CONTEXT_FIELDS:
            properties.pop(field, None)
    required = cleaned.get("required")
    if isinstance(required, list):
        cleaned["required"] = [field for field in required if field not in CONTEXT_FIELDS]
    cleaned.pop("title", None)
    return cleaned


def inject_tool_context(arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    """Mescla argumentos do modelo com os valores oficiais e autenticados de ToolContext.

    A sobreposição é estrita: os valores do ToolContext autenticado sempre
    prevalecem sobre quaisquer campos homônimos enviados pelo LLM.
    """
    context_dict = context.model_dump(mode="json", include=set(CONTEXT_FIELDS))
    return {**arguments, **context_dict}


TOOL_DEFINITIONS = [
    (
        "consultar_processo",
        "Consulte os metadados, a cobertura da exportação e o inventário do processo "
        "autorizado; inventário vazio não prova ausência no processo original.",
        ToolContext,
    ),
    (
        "buscar_documentos",
        "Busque texto literal nos trechos do corpus autorizado para localizar fontes. "
        "Uma busca sem resultados não prova ausência no processo original.",
        SearchInput,
    ),
    (
        "ler_documento",
        "Leia o conteúdo e a origem de um documento do corpus autorizado, inteiro ou "
        "apenas nas páginas informadas.",
        ReadInput,
    ),
    (
        "consultar_requisitos",
        "Consulte os requisitos do checklist associado à versão do processo antes de "
        "avaliar ou registrar uma pendência.",
        ToolContext,
    ),
    (
        "registrar_pendencia",
        "Registre uma pendência fundamentada em requisito do checklist e evidências "
        "válidas; use a mesma chave de idempotência para repetir a mesma escrita.",
        PendencyInput,
    ),
    (
        "salvar_minuta",
        "Salve uma minuta fundamentada em evidências válidas e receba o comprovante "
        "de persistência; use a mesma chave de idempotência para repetir a mesma escrita.",
        WriteInput,
    ),
]


def _load_shared_catalog_module() -> Any | None:
    try:
        return importlib.import_module("contracts.catalog")
    except ImportError:
        return None


def tool_catalog() -> list[dict[str, Any]]:
    """Retorna o catálogo canônico de ferramentas sem expor ToolContext ao LLM."""
    shared = _load_shared_catalog_module()
    if shared is not None and callable(getattr(shared, "tool_catalog", None)):
        return list(shared.tool_catalog())
    return [
        {
            "name": name,
            "description": description,
            "parameters": _clean_schema(model.model_json_schema()),
        }
        for name, description, model in TOOL_DEFINITIONS
    ]


def openai_tools() -> list[dict[str, Any]]:
    """Catálogo no formato de function calling (/chat/completions)."""
    shared = _load_shared_catalog_module()
    if shared is not None and callable(getattr(shared, "openai_tools", None)):
        return list(shared.openai_tools())
    return [{"type": "function", "function": item} for item in tool_catalog()]


def hermes_tool_schemas() -> list[dict[str, Any]]:
    """Gera o catálogo das 6 ferramentas no formato OpenAI sem expor ToolContext ao LLM."""
    return openai_tools()


def catalog_version() -> str:
    """SHA-256 do catálogo em JSON canônico para registro em ExperimentRun.parameters."""
    shared = _load_shared_catalog_module()
    if shared is not None and callable(getattr(shared, "catalog_version", None)):
        return str(shared.catalog_version())
    canonical = json.dumps(
        tool_catalog(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


TOOLS = hermes_tool_schemas()

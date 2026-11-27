"""Verifica os schemas de ferramentas, catálogo compartilhado e injeção de contexto do Hermes."""

import re
from types import SimpleNamespace
from uuid import uuid4

from agents.hermes.tools import (
    TOOLS,
    catalog_version,
    hermes_tool_schemas,
    inject_tool_context,
    openai_tools,
    tool_catalog,
)
from contracts.models import ToolContext

EXPECTED_TOOL_NAMES = [
    "consultar_processo",
    "buscar_documentos",
    "ler_documento",
    "consultar_requisitos",
    "registrar_pendencia",
    "salvar_minuta",
]

CONTEXT_FIELDS = {"run_id", "process_id", "corpus_version", "requirements_version"}


def test_hermes_tool_schemas_returns_all_six_tools():
    schemas = hermes_tool_schemas()
    assert len(schemas) == 6
    names = [s["function"]["name"] for s in schemas]
    assert names == EXPECTED_TOOL_NAMES

    for definition in schemas:
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"] in EXPECTED_TOOL_NAMES
        assert function["description"]
        assert isinstance(function["parameters"], dict)
        assert function["parameters"]["type"] == "object"
        assert "title" not in function["parameters"]

    # Garante retrocompatibilidade do alias TOOLS e equivalência com openai_tools
    assert TOOLS == schemas
    assert openai_tools() == schemas
    assert [item["function"] for item in schemas] == tool_catalog()


def test_catalog_version_returns_stable_sha256_and_supports_shared_catalog(monkeypatch):
    version = catalog_version()
    assert re.fullmatch(r"[a-f0-9]{64}", version)
    assert catalog_version() == version

    fake_shared = SimpleNamespace(
        tool_catalog=lambda: [{"name": "consultar_processo", "description": "x", "parameters": {}}],
        openai_tools=lambda: [
            {
                "type": "function",
                "function": {"name": "consultar_processo", "description": "x", "parameters": {}},
            }
        ],
        catalog_version=lambda: "f" * 64,
    )
    monkeypatch.setattr("agents.hermes.tools._load_shared_catalog_module", lambda: fake_shared)
    assert catalog_version() == "f" * 64
    assert len(tool_catalog()) == 1
    assert len(openai_tools()) == 1


def test_hermes_tool_schemas_omit_context_fields_from_properties_and_required():
    schemas = hermes_tool_schemas()
    schemas_by_name = {s["function"]["name"]: s["function"]["parameters"] for s in schemas}

    for name, parameters in schemas_by_name.items():
        properties = parameters.get("properties", {})
        required = parameters.get("required", [])

        for field in ("run_id", "process_id"):
            assert field not in properties, (
                f"Campo '{field}' não deve estar em 'properties' da ferramenta '{name}'"
            )
            assert field not in required, (
                f"Campo '{field}' não deve estar em 'required' da ferramenta '{name}'"
            )

        for context_field in CONTEXT_FIELDS:
            assert context_field not in properties, (
                f"Contexto '{context_field}' indevido em 'properties' de '{name}'"
            )
            assert context_field not in required, (
                f"Contexto '{context_field}' indevido em 'required' de '{name}'"
            )

    # Ferramentas sem parâmetros específicos expõem properties vazias
    assert schemas_by_name["consultar_processo"]["properties"] == {}
    assert schemas_by_name["consultar_requisitos"]["properties"] == {}

    # Ferramentas com parâmetros específicos preservam suas propriedades de negócio
    assert "query" in schemas_by_name["buscar_documentos"]["properties"]
    assert "query" in schemas_by_name["buscar_documentos"]["required"]

    assert "document_id" in schemas_by_name["ler_documento"]["properties"]
    assert "document_id" in schemas_by_name["ler_documento"]["required"]

    for write_tool in ("registrar_pendencia", "salvar_minuta"):
        props = schemas_by_name[write_tool]["properties"]
        req = schemas_by_name[write_tool]["required"]
        for expected_prop in ("idempotency_key", "content", "evidence", "evidence_note"):
            assert expected_prop in props, f"Propriedade '{expected_prop}' esperada em {write_tool}"
            assert expected_prop in req, f"Propriedade '{expected_prop}' requerida em {write_tool}"


def test_inject_tool_context_overrides_model_supplied_context_fields():
    context = ToolContext(
        run_id=uuid4(),
        process_id="PROC-AUTH-123",
        corpus_version="synthetic-v1",
        requirements_version="demo-v1",
    )

    adversarial_arguments = {
        "run_id": "00000000-0000-0000-0000-000000000000",
        "process_id": "PROC-HACKED-999",
        "corpus_version": "malicious-corpus",
        "requirements_version": "malicious-req",
        "query": "documentos de habilitação",
        "limit": 10,
    }

    injected = inject_tool_context(adversarial_arguments, context)

    # Valores oficiais do ToolContext autenticado SEMPRE sobrepõem os enviados pelo LLM
    assert injected["run_id"] == str(context.run_id)
    assert injected["run_id"] != adversarial_arguments["run_id"]
    assert injected["process_id"] == "PROC-AUTH-123"
    assert injected["process_id"] != adversarial_arguments["process_id"]
    assert injected["corpus_version"] == "synthetic-v1"
    assert injected["requirements_version"] == "demo-v1"

    # Parâmetros legítimos de negócio enviados pelo LLM são preservados
    assert injected["query"] == "documentos de habilitação"
    assert injected["limit"] == 10

    # Garante que os argumentos originais não foram mutados
    assert adversarial_arguments["run_id"] == "00000000-0000-0000-0000-000000000000"
    assert adversarial_arguments["process_id"] == "PROC-HACKED-999"

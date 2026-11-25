"""Catálogo único de tools para Hermes e LangGraph (validação K)."""

import json
import re

from contracts.catalog import TOOLS, catalog_version, openai_tools, tool_catalog
from contracts.models import ToolContext


def test_openai_tools_wrap_the_shared_catalog_without_changes():
    tools = openai_tools()
    assert [item["type"] for item in tools] == ["function"] * len(TOOLS)
    assert [item["function"] for item in tools] == tool_catalog()
    assert {item["function"]["name"] for item in tools} == set(TOOLS)


def test_openai_tools_never_expose_authenticated_context():
    for item in openai_tools():
        parameters = item["function"]["parameters"]
        assert parameters["type"] == "object"
        assert not set(ToolContext.model_fields) & set(parameters["properties"])
        assert not set(ToolContext.model_fields) & set(parameters.get("required", []))
        # Serializável para o corpo de /chat/completions.
        json.dumps(item, ensure_ascii=False)


def test_catalog_version_is_stable_and_tracks_content(monkeypatch):
    version = catalog_version()
    assert re.fullmatch(r"[a-f0-9]{64}", version)
    assert catalog_version() == version
    changed = [{**tool_catalog()[0], "description": "outra"}, *tool_catalog()[1:]]
    monkeypatch.setattr("contracts.catalog.tool_catalog", lambda: changed)
    assert catalog_version() != version

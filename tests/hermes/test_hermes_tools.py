"""Verifica os schemas de ferramentas expostos pelo adaptador Hermes."""

from agents.hermes.tools import TOOLS
from contracts.models import ReadInput, SearchInput, ToolContext


def test_hermes_read_tools_use_openai_function_calling_schemas():
    expected = [
        ("consultar_processo", ToolContext),
        ("buscar_documentos", SearchInput),
        ("ler_documento", ReadInput),
    ]

    assert len(TOOLS) == len(expected)
    for definition, (name, input_model) in zip(TOOLS, expected, strict=True):
        assert definition["type"] == "function"
        function = definition["function"]
        assert function["name"] == name
        assert function["description"]
        assert function["parameters"] == input_model.model_json_schema()

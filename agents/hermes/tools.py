"""Schemas das ferramentas de leitura no formato OpenAI function calling."""

from contracts.models import ReadInput, SearchInput, ToolContext

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_processo",
            "description": "Consulta os metadados do processo no contexto informado.",
            "parameters": ToolContext.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_documentos",
            "description": (
                "Busca trechos literais nos documentos do processo e corpus informados."
            ),
            "parameters": SearchInput.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ler_documento",
            "description": (
                "Retorna o documento completo, com páginas, do processo e corpus informados."
            ),
            "parameters": ReadInput.model_json_schema(),
        },
    },
]

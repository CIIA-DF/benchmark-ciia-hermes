"""Confere cobertura das fichas e exemplos documentais contra as rotas locais."""

import json
from pathlib import Path

from sqlalchemy import create_engine

from contracts import execution, models
from services.backend.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def validate() -> int:
    entries = json.loads(
        (ROOT / "docs/02-arquitetura/backend-api-exemplos.json").read_text(encoding="utf-8")
    )
    reference = (ROOT / "docs/02-arquitetura/backend-api-atual.md").read_text(encoding="utf-8")
    engine = create_engine("sqlite://")
    try:
        api = create_app(engine).openapi()
    finally:
        engine.dispose()
    expected = {
        (method.upper(), path) for path, methods in api["paths"].items() for method in methods
    }
    actual = {(entry["method"], entry["path"]) for entry in entries}
    if actual != expected or len(entries) != len(actual):
        raise ValueError("Cobertura documental diverge das operações OpenAPI.")
    for entry in entries:
        method, path = entry["method"], entry["path"]
        operation = api["paths"][path][method.lower()]
        if f"### {method} `{path}`" not in reference:
            raise ValueError(f"Ficha ausente: {method} {path}")
        section = reference.split(f"### {method} `{path}`", 1)[1].split("\n##", 1)[0]
        for status in operation["responses"]:
            if f"| {status} |" not in section:
                raise ValueError(f"Status ausente na ficha: {method} {path}: {status}")
        if entry["responses"] != sorted(operation["responses"]):
            raise ValueError(f"Respostas divergentes: {method} {path}")
        if entry["parameters"] != [p["name"] for p in operation.get("parameters", [])]:
            raise ValueError(f"Parâmetros divergentes: {method} {path}")
        schema = (
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        name = schema.get("$ref", "").split("/")[-1] or None
        if entry["input_model"] != name:
            raise ValueError(f"Modelo divergente: {method} {path}")
        if name:
            model = getattr(models, name, None) or getattr(execution, name)
            model.model_validate(entry["example"])
            example = json.dumps(entry["example"], ensure_ascii=False, indent=2)
            if f"```json\n{example}\n```" not in section:
                raise ValueError(f"Exemplo da ficha diverge: {method} {path}")
    return len(entries)


if __name__ == "__main__":
    print(f"{validate()} operações documentadas; exemplos válidos nos modelos atuais.")

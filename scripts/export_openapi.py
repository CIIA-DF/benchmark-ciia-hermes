"""Exporta o OpenAPI gerado pela aplicação; --check falha se o arquivo versionado divergir."""

import argparse
import sys
from pathlib import Path

import yaml
from sqlalchemy import create_engine

from services.backend.app import create_app

TARGET = Path(__file__).resolve().parents[1] / "services" / "backend" / "openapi.yaml"


def render():
    # O schema não consulta o banco; o engine em memória evita depender de DATABASE_URL.
    schema = create_app(create_engine("sqlite://")).openapi()
    schema["servers"] = [{"url": "http://127.0.0.1:8000", "description": "Backend local"}]
    return yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=100)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            sys.exit(f"{TARGET.name} desatualizado; rode: python -m scripts.export_openapi")
        print(f"{TARGET.name} atualizado")
        return
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"Gravado {TARGET}")


if __name__ == "__main__":
    main()

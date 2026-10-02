"""Exercita apenas a interface HTTP; não simula raciocínio ou resultado de um agente."""

import argparse
import json
import os
from uuid import uuid4

from agents.interface import ToolClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=["hermes", "langgraph"])
    args = parser.parse_args()
    result = ToolClient(os.getenv("BACKEND_URL", "http://127.0.0.1:8000")).call(
        "consultar_processo",
        {
            "run_id": str(uuid4()),
            "process_id": "PROC-DEMO-001",
            "corpus_version": "synthetic-v1",
            "requirements_version": "demo-v1",
        },
    )
    print(f"Teste de interface para {args.adapter}; integração com executor ainda pendente.")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

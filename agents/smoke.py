"""Exercita apenas a interface HTTP; não simula raciocínio ou resultado de um agente."""

import argparse
import json
import os

import httpx

from scripts.demo import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=["hermes", "langgraph"])
    args = parser.parse_args()
    with httpx.Client(
        base_url=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"), timeout=15
    ) as client:
        result = verify(
            client, os.environ["BACKEND_OPERATOR_TOKEN"], os.environ["BACKEND_WORKER_TOKEN"]
        )
    print(f"Teste de interface para {args.adapter}; integração com executor ainda pendente.")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

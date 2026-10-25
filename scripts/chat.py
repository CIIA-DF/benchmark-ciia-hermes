"""Configuração e execução local do chat. Segredos gerados ficam em arquivos ignorados."""

import argparse
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/chat.env"


def load(path=CONFIG):
    if not path.exists():
        raise SystemExit("Execute primeiro: uv run --locked python -m scripts.chat setup")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def setup():
    if not CONFIG.exists():
        CONFIG.parent.mkdir(exist_ok=True)
        values = {
            "POSTGRES_USER": "benchmark",
            "POSTGRES_DB": "benchmark",
            "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "BACKEND_OPERATOR_TOKEN": secrets.token_urlsafe(32),
            "BACKEND_WORKER_TOKEN": secrets.token_urlsafe(32),
            "BACKEND_URL": "http://127.0.0.1:8000",
        }
        CONFIG.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    load()
    portal_config = ROOT / "portal/.env.local"
    if not portal_config.exists():
        portal_config.write_text(
            f"BACKEND_URL={os.environ['BACKEND_URL']}\n"
            f"BACKEND_OPERATOR_TOKEN={os.environ['BACKEND_OPERATOR_TOKEN']}\n",
            encoding="utf-8",
        )
    print("Configuração privada criada/preservada em data/chat.env e portal/.env.local.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "serve", "worker", "verify", "up", "down"])
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.command == "setup":
        setup()
        return
    load()
    if args.command == "serve":
        from scripts.demo import seed

        seed()
        subprocess.run([sys.executable, "-m", "scripts.dev", "serve"], check=True)
    elif args.command == "verify":
        import json

        import httpx

        from scripts.demo import verify

        with httpx.Client(base_url=os.environ["BACKEND_URL"], timeout=30) as client:
            result = verify(
                client, os.environ["BACKEND_OPERATOR_TOKEN"], os.environ["BACKEND_WORKER_TOKEN"]
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "worker":
        from agents.worker import main as worker_main

        # argparse do worker não deve receber o subcomando deste lançador.
        sys.argv = ["agents.worker"]
        worker_main()
    else:
        command = [
            "docker",
            "compose",
            "--project-name",
            "ciia-chat-local",
            "--env-file",
            str(CONFIG),
            "-f",
            "infra/compose.yml",
        ]
        command += ["up", "--build", "--wait"] if args.command == "up" else ["down"]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()

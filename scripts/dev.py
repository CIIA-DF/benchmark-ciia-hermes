"""Comandos iguais para Windows, Linux e macOS: uv run python -m scripts.dev check."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str):
    subprocess.run(command, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "setup",
            "up",
            "down",
            "demo",
            "demo-compose",
            "check",
            "test-backend",
            "test-documents",
            "test-integration",
            "serve",
        ],
    )
    args = parser.parse_args()
    python = sys.executable
    try:
        if args.command == "setup":
            run("uv", "sync", "--locked")
        elif args.command in {"up", "down", "demo-compose"}:
            if not shutil.which("docker"):
                parser.exit(
                    1, "Docker não encontrado. Use a demo local ou instale Docker Compose.\n"
                )
            compose = ("docker", "compose", "--env-file", ".env", "-f", "infra/compose.yml")
            if not (ROOT / ".env").exists():
                parser.exit(1, "Copie .env.example para .env e defina POSTGRES_PASSWORD.\n")
            if args.command == "up":
                run(*compose, "up", "--build", "--wait")
            elif args.command == "down":
                run(*compose, "down")
            else:
                run(
                    *compose, "exec", "-T", "backend", "python", "-m", "scripts.demo", "--seed-only"
                )
                run(python, "-m", "scripts.demo", "--url", "http://127.0.0.1:8000")
        elif args.command == "demo":
            run(python, "-m", "scripts.demo")
        elif args.command == "serve":
            run(
                python,
                "-m",
                "uvicorn",
                "services.backend.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
                "--no-access-log",
            )
        elif args.command == "check":
            run(python, "-m", "ruff", "check", ".")
            run(python, "-m", "ruff", "format", "--check", ".")
            run(python, "-m", "scripts.validate_repository")
            run(python, "-m", "pytest")
        else:
            run(python, "-m", "pytest", "tests/" + args.command.removeprefix("test-"))
    except FileNotFoundError as exc:
        parser.exit(1, f"Comando ausente: {exc.filename}. Consulte docs/getting-started.md.\n")
    except subprocess.CalledProcessError as exc:
        parser.exit(
            exc.returncode, f"Comando falhou (código {exc.returncode}). Veja o erro acima.\n"
        )


if __name__ == "__main__":
    main()

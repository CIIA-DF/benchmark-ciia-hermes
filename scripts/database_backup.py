"""Backup binário sem redirecionamento de shell e restauração em banco novo de teste."""

import argparse
import subprocess
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore-test"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--project-name")
    args = parser.parse_args()
    compose = ["docker", "compose", "--env-file", args.env_file, "-f", "infra/compose.yml"]
    if args.project_name:
        compose += ["--project-name", args.project_name]
    try:
        if args.operation == "backup":
            args.file.parent.mkdir(parents=True, exist_ok=True)
            # Modo exclusivo: jamais sobrescrever um backup anterior.
            with args.file.open("xb") as output:
                subprocess.run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "db",
                        "sh",
                        "-c",
                        'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" '
                        "-Fc --no-owner --no-privileges",
                    ],
                    cwd=ROOT,
                    stdout=output,
                    check=True,
                )
            print(f"Backup concluído: {args.file}. Confirme com restore-test.")
        else:
            with args.file.open("rb") as source:
                target = "restore_check_" + uuid4().hex[:12]
                subprocess.run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "db",
                        "sh",
                        "-c",
                        'createdb -U "$POSTGRES_USER" "$1"',
                        "sh",
                        target,
                    ],
                    cwd=ROOT,
                    check=True,
                )
                subprocess.run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "db",
                        "sh",
                        "-c",
                        'pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner '
                        "--no-privileges --exit-on-error",
                        "sh",
                        target,
                    ],
                    cwd=ROOT,
                    stdin=source,
                    check=True,
                )
                subprocess.run(
                    [
                        *compose,
                        "exec",
                        "-T",
                        "db",
                        "sh",
                        "-c",
                        'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -c '
                        "'SELECT (SELECT count(*) FROM processes) AS processes, "
                        "(SELECT count(*) FROM documents) AS documents, "
                        "(SELECT count(*) FROM chunks) AS chunks, "
                        "(SELECT count(*) FROM conversations) AS conversations, "
                        "(SELECT count(*) FROM messages) AS messages, "
                        "(SELECT count(*) FROM runs) AS runs, "
                        "(SELECT count(*) FROM run_events) AS run_events, "
                        "(SELECT count(*) FROM artifacts) AS artifacts;'",
                        "sh",
                        target,
                    ],
                    cwd=ROOT,
                    check=True,
                )
                print(f"Restaurado em {target}; original preservado. Registre e gerencie o teste.")
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.exit(
            1,
            f"Falha de backup/restauração: {exc}. "
            "Arquivo parcial ou banco de teste pode permanecer; não use como backup validado.\n",
        )


if __name__ == "__main__":
    main()

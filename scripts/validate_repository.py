"""Verifica links locais, YAML e invariantes dos workflows sem acesso remoto."""

import re
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]


def validate() -> list[str]:
    errors = []
    for path in ROOT.rglob("*.md"):
        if any(part in {".venv", ".git", ".pytest_cache"} for part in path.parts):
            continue
        content = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", content):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / unquote(target)).exists():
                errors.append(f"{path.relative_to(ROOT)}: link ausente {target}")
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        # BaseLoader mantém 'on' como string (SafeLoader usa regras YAML 1.1).
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        if not isinstance(workflow, dict) or not {"on", "jobs", "permissions"} <= workflow.keys():
            errors.append(f"Workflow incompleto: {path.name}")
    ci = yaml.load((ROOT / ".github/workflows/ci.yml").read_text(), Loader=yaml.BaseLoader)
    if not {"pull_request", "push"} <= ci["on"].keys():
        errors.append("CI precisa cobrir pull_request e push.")
    if set(ci["jobs"]) != {"quality", "integration"}:
        errors.append("Nomes obrigatórios dos checks mudaram.")
    compose = yaml.safe_load((ROOT / "infra/compose.yml").read_text(encoding="utf-8"))
    if compose["services"]["db"].get("ports"):
        errors.append("O banco não deve publicar portas no Compose.")
    return errors


if __name__ == "__main__":
    failures = validate()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Links locais, YAML e invariantes dos workflows válidos.")

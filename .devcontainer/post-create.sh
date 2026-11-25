#!/usr/bin/env bash
# Prepara o sandbox: dependências pelo lock, sem atualizar versões.
set -euo pipefail
for dir in .venv portal/node_modules; do
  [ -w "$dir" ] || { echo "Sem permissão de escrita em $dir; recrie os volumes do sandbox." >&2; exit 1; }
done
uv sync --locked
(cd portal && npm ci --no-audit --no-fund)
uv run --locked ruff check .
uv run --locked python -m scripts.validate_repository
# Demo no PostgreSQL do sandbox (DATABASE_URL vem do .devcontainer/compose.yml).
uv run --locked python -m scripts.demo
cat <<'EOF'
Sandbox pronto.
  Suíte completa (PostgreSQL do sandbox): uv run --locked python -m scripts.dev check
  Backend local:                          uv run --locked python -m scripts.dev serve
EOF

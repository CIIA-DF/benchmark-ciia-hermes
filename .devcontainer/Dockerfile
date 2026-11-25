# Mesmas versões da imagem do backend (infra/Dockerfile) e do portal (infra/portal.Dockerfile).
FROM python:3.12-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /usr/local/bin/uv
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash vscode \
    # Pontos de montagem dos volumes: um volume novo herda dono e permissões daqui.
    && mkdir -p /workspaces/benchmark-ciia-hermes/.venv \
        /workspaces/benchmark-ciia-hermes/portal/node_modules \
    && chown -R vscode:vscode /workspaces
USER vscode

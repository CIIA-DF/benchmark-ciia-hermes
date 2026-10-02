FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY contracts ./contracts
COPY services ./services
COPY pipelines ./pipelines
COPY scripts ./scripts
COPY examples ./examples
RUN useradd --create-home app
USER app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
CMD ["python", "-m", "uvicorn", "services.backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

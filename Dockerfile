FROM python:3.13.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.9.2 /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini README.md ./
RUN uv sync --frozen --no-dev && useradd --create-home --uid 10001 app
USER app
CMD ["python", "-m", "payment_processor.api"]

FROM ghcr.io/astral-sh/uv:0.11.25 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY reviewer ./reviewer
COPY services ./services
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY db ./db
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home app && chown -R app:app /app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]

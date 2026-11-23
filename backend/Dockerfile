# HappySmile backend: FastAPI web server + call worker (RUN_WORKER=true) for Railway or any container host.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"

# Dependencies first (cached between deploys), then the app.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev && sed -i 's/\r$//' start.sh

RUN useradd --create-home app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "start.sh"]

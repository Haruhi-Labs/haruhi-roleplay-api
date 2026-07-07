FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    ROLEPLAY_HOST=0.0.0.0 \
    ROLEPLAY_PORT=8000 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY personas ./personas
COPY frontend-demo ./frontend-demo

EXPOSE 8000

CMD ["uv", "run", "--frozen", "python", "-m", "haruhi_roleplay_api.infrastructure.http_server"]

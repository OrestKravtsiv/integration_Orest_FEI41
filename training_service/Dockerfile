FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --group training --no-install-project

COPY training_service/app ./app
COPY training_service/data ./data

RUN uv sync --frozen --group training

CMD ["uv", "run", "python", "-m", "app.train"]

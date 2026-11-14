FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Attente des services = scripts/wait_for.py (stdlib).
# apt-get nécessaire pour WeasyPrint (libs de rendu, pas de wheel possible) —
# fonctionne car le build tourne en network: host (voir docker-compose.yml).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh docker-entrypoint-worker.sh ./

RUN chmod +x docker-entrypoint.sh docker-entrypoint-worker.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]

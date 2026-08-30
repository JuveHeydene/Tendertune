FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Pas d'apt-get : évite deb.debian.org (DNS Docker souvent cassé).
# Attente des services = scripts/wait_for.py (stdlib).

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh docker-entrypoint-worker.sh ./

RUN chmod +x docker-entrypoint.sh docker-entrypoint-worker.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]

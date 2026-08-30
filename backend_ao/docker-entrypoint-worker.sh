#!/bin/sh
set -eu

POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-redis}"
REDIS_PORT="${REDIS_PORT:-6379}"
MINIO_HOST="${MINIO_HOST:-minio}"
MINIO_PORT="${MINIO_PORT:-9000}"
QDRANT_HOST="${QDRANT_HOST:-qdrant}"
QDRANT_PORT="${QDRANT_PORT:-6333}"

echo "=== Démarrage worker ARQ ==="

python scripts/wait_for.py PostgreSQL "$POSTGRES_HOST" "$POSTGRES_PORT" 60
python scripts/wait_for.py Redis "$REDIS_HOST" "$REDIS_PORT" 30
python scripts/wait_for.py MinIO "$MINIO_HOST" "$MINIO_PORT" 30
python scripts/wait_for.py Qdrant "$QDRANT_HOST" "$QDRANT_PORT" 30

echo "[run] buckets MinIO (idempotent)"
python scripts/create_buckets.py

echo "[run] arq app.worker_settings.WorkerSettings"
exec arq app.worker_settings.WorkerSettings

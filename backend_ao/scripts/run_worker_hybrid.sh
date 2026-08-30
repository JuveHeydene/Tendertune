#!/usr/bin/env bash
# Worker ARQ hybride : tourne sur l'hôte avec Docling + PaddleOCR (GPU si USE_GPU=true).
# Infra (Postgres, Redis, MinIO, Qdrant, Neo4j) reste en Docker.
# Couper le worker Docker avant : docker compose --profile dev stop worker
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/backend_ao"
ENV_FILE="$ROOT/.env"
VENV="$BACKEND/.venv"
PY="$VENV/lib/python3.12/site-packages"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Fichier .env introuvable : $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export USE_GPU="${USE_GPU:-false}"
export PYTHONUNBUFFERED=1

# Bibliothèques NVIDIA embarquées dans le venv (cuDNN 8.9 pour Paddle 2.6 GPU).
if [[ -d "$PY/nvidia" ]]; then
  NVIDIA_LIBS=""
  while IFS= read -r libdir; do
    NVIDIA_LIBS="${libdir}:${NVIDIA_LIBS}"
  done < <(find "$PY/nvidia" -type d -name lib 2>/dev/null)
  export LD_LIBRARY_PATH="${NVIDIA_LIBS}${LD_LIBRARY_PATH:-}"
fi

echo "=== Worker ARQ hybride BTP_RAG ==="
echo "USE_GPU=$USE_GPU"
echo "REDIS_URL=$REDIS_URL"
echo "DATABASE_URL=${DATABASE_URL%%@*}@***"
echo "OLLAMA_BASE_URL=$OLLAMA_BASE_URL"
if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
  echo "LD_LIBRARY_PATH configuré (nvidia/cudnn dans le venv)"
fi
echo "=================================="

cd "$BACKEND"
exec "$VENV/bin/python" -m arq app.worker_settings.WorkerSettings

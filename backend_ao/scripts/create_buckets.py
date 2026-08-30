"""Crée ao-raw et ao-exports. Appelé par les docker-entrypoint (pas à la main)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.minio_client import ensure_buckets  # noqa: E402


if __name__ == "__main__":
    ensure_buckets()
    print("OK — buckets MinIO prêts.")

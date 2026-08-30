"""Client MinIO — buckets créés au démarrage (entrypoint + lifespan)."""

import time

from minio import Minio
from minio.error import S3Error

from app.config import get_settings


def get_minio() -> Minio:
    s = get_settings()
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_use_ssl,
    )


def ensure_buckets(*, retries: int = 15, delay: float = 2.0) -> None:
    """Idempotent. Réessaie : MinIO accepte TCP avant que l'API S3 soit prête."""
    s = get_settings()
    names = (s.minio_bucket_raw, s.minio_bucket_export)
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            client = get_minio()
            client.list_buckets()
            for name in names:
                if not client.bucket_exists(name):
                    client.make_bucket(name)
                    print(f"[minio] bucket créé : {name}")
                else:
                    print(f"[minio] bucket déjà présent : {name}")
            return
        except (S3Error, OSError) as exc:
            last_error = exc
            print(f"[minio] tentative {attempt}/{retries} : {exc}")
            time.sleep(delay)

    raise RuntimeError(f"MinIO indisponible après {retries} tentatives") from last_error

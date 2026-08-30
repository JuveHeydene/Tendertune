"""File d’attente ARQ (Redis)."""

import logging

from arq import create_pool
from arq.connections import ArqRedis

from app.worker_settings import _redis_settings

log = logging.getLogger("btp.queue")

_pool: ArqRedis | None = None


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(_redis_settings())
        log.info("pool ARQ ouvert")
    return _pool


async def enqueue_ingest(document_id: str) -> str | None:
    redis = await get_queue()
    job = await redis.enqueue_job("ingest_document", document_id)
    job_id = getattr(job, "job_id", None)
    log.info("enqueue ingest_document document_id=%s job_id=%s", document_id, job_id)
    return str(job_id) if job_id else None


async def enqueue_extract_structure(dossier_id: str) -> str | None:
    """§9 — déclenche l'extraction outline/exigences/pièces administratives.
    Déterministe (comme extract_graph), simplement exposée via un job pour
    ne pas bloquer une requête HTTP sur un DAO de 200 pages."""
    redis = await get_queue()
    job = await redis.enqueue_job("extract_dossier_structure", dossier_id)
    job_id = getattr(job, "job_id", None)
    log.info("enqueue extract_dossier_structure dossier_id=%s job_id=%s", dossier_id, job_id)
    return str(job_id) if job_id else None

"""Réglages ARQ. Lancer : uv run arq app.worker_settings.WorkerSettings"""

from urllib.parse import urlparse
import logging

from arq.connections import RedisSettings

from app.config import get_settings
from app.graph.extract import extract_graph
from app.services.logging_setup import configure_logging
from app.workers.ingest import ingest_document
from app.workflow.extract_structure import extract_dossier_structure


async def on_startup(ctx: dict) -> None:
    configure_logging()
    logging.getLogger("btp.ingest").info(
        "worker ARQ prêt — jobs ingest_document + extract_graph + extract_dossier_structure"
    )


def _redis_settings() -> RedisSettings:
    parsed = urlparse(get_settings().redis_url)
    db = parsed.path.lstrip("/") or "0"
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password,
        database=int(db),
    )


class WorkerSettings:
    functions = [ingest_document, extract_graph, extract_dossier_structure]
    redis_settings = _redis_settings()
    max_jobs = 2
    job_timeout = 3600
    on_startup = on_startup

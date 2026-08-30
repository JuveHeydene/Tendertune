"""Point d'entrée HTTP. FastAPI ne parse pas les PDF : il délègue aux workers."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, conversations, dashboard, documents, dossiers, exports
from app.config import get_settings
from app.services.db_client import get_session
from app.services.logging_setup import configure_logging
from app.services.minio_client import ensure_buckets
from app.services.seed import bootstrap_platform

log = logging.getLogger("btp.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info(
        "démarrage — GPU=%s device=%s llm=%s/%s embed=%s/%s",
        settings.use_gpu,
        settings.device,
        settings.llm_provider,
        settings.llm_model,
        settings.embed_provider,
        settings.embed_model,
    )
    try:
        ensure_buckets()
        log.info("MinIO buckets OK")
    except Exception as exc:
        log.warning("MinIO warning : %s", exc)
    try:
        async for session in get_session():
            await bootstrap_platform(session)
            break
        log.info("admin bootstrap : %s", get_settings().admin_email)
    except Exception as exc:
        log.warning("seed utilisateurs : %s", exc)
    yield


app = FastAPI(
    title="BTP RAG — Appels d'offres",
    description=(
        "Porte HTTP : upload, chat, workflow dossier, export. "
        "Le RAG vit dans app/rag/, l'orchestration dans app/workflow/."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(documents.router)
app.include_router(exports.router)
app.include_router(conversations.router)
app.include_router(dossiers.router)


@app.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "use_gpu": settings.use_gpu,
        "device": settings.device,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embed_provider": settings.embed_provider,
        "embed_model": settings.embed_model,
        "ollama_base_url": settings.ollama_base_url,
    }

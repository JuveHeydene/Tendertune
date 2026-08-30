"""Création document MinIO + Postgres + file ARQ (partagé upload tenant / conversation)."""

from __future__ import annotations

import logging
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Document, User
from app.services.minio_client import get_minio
from app.services.queue import enqueue_ingest

log = logging.getLogger("btp.upload")


async def store_document(
    session: AsyncSession,
    user: User,
    data: bytes,
    filename: str,
    *,
    doc_role: str,
    doc_type: str | None,
    content_type: str | None = None,
    dossier_origine_id: UUID | None = None,
    dossier_id: UUID | None = None,
) -> tuple[Document, bool]:
    """Retourne (document, duplicate)."""
    digest = sha256(data).hexdigest()
    existing = (
        await session.execute(
            select(Document).where(Document.tenant_id == user.tenant_id, Document.sha == digest)
        )
    ).scalar_one_or_none()
    if existing:
        log.info("store_document doublon sha=%s id=%s", digest[:12], existing.id)
        return existing, True

    object_key = f"{user.tenant_id}/{uuid4()}/{filename}"
    settings = get_settings()
    get_minio().put_object(
        settings.minio_bucket_raw,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )
    doc = Document(
        tenant_id=user.tenant_id,
        created_by=user.id,
        object_key=object_key,
        sha=digest,
        doc_role=doc_role,
        doc_type=doc_type,
        is_dao=doc_role in ("dao_courant", "dao_archive"),
        dossier_origine_id=dossier_origine_id,
        # V2 — doc_role="annexe" : scope live au dossier (§1.5), distinct de
        # dossier_origine_id (provenance historique d'un doc de patrimoine).
        dossier_id=dossier_id,
        status="pending",
        filename=filename,
        size_bytes=len(data),
        mime_type=content_type,
    )
    session.add(doc)
    await session.flush()
    try:
        await enqueue_ingest(str(doc.id))
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        log.exception("store_document ARQ échec id=%s", doc.id)
        doc.status = "failed"
        doc.ingest_error = f"File Redis/ARQ : {err}"[:4000]
    return doc, False

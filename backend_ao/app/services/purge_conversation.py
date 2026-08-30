"""Suppression conversation : messages (CASCADE) + dossier lié si orphelin + exports MinIO."""

from __future__ import annotations

import logging
from uuid import UUID

from minio.error import S3Error
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Conversation, Dossier, Export
from app.services.minio_client import get_minio

log = logging.getLogger("btp.purge")


def _delete_export_object(object_key: str) -> None:
    s = get_settings()
    try:
        get_minio().remove_object(s.minio_bucket_export, object_key)
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            return
        raise


async def _purge_dossier_if_orphan(session: AsyncSession, dossier_id: UUID) -> None:
    others = (
        await session.execute(
            select(func.count()).select_from(Conversation).where(Conversation.dossier_id == dossier_id)
        )
    ).scalar_one()
    if others:
        log.info("dossier %s conservé — %s autre(s) conversation(s)", dossier_id, others)
        return

    doss = await session.get(Dossier, dossier_id)
    if doss is None:
        return

    exports = (
        await session.execute(select(Export.object_key).where(Export.dossier_id == dossier_id))
    ).scalars().all()
    for key in exports:
        log.info("MinIO export DELETE key=%s", key)
        _delete_export_object(key)

    log.info("Postgres dossier DELETE id=%s (outline, generations, exports en CASCADE)", dossier_id)
    await session.delete(doss)


async def purge_conversation(session: AsyncSession, conv: Conversation) -> None:
    dossier_id = conv.dossier_id
    conv_id = conv.id
    log.info("======== PURGE CONVERSATION DÉBUT id=%s dossier=%s ========", conv_id, dossier_id)

    await session.delete(conv)
    await session.flush()

    if dossier_id is not None:
        await _purge_dossier_if_orphan(session, dossier_id)

    await session.commit()
    log.info("======== PURGE CONVERSATION FIN id=%s ========", conv_id)

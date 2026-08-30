"""Suppression d’un document : MinIO + Qdrant + Neo4j + Postgres (chunks en cascade)."""

from __future__ import annotations

import logging
from uuid import UUID

from minio.error import S3Error
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.graph.extract import _driver
from app.models.sql import ChunkRow, Document
from app.services.minio_client import get_minio

log = logging.getLogger("btp.purge")


def can_delete_document(user) -> bool:
    if user.role == "admin":
        return True
    if user.role != "manager":
        return False
    perms = user.permissions or {}
    if "can_delete" in perms:
        return bool(perms["can_delete"])
    return True


def _delete_minio(object_key: str) -> None:
    s = get_settings()
    log.info("[3/4] MinIO DELETE DÉBUT bucket=%s key=%s", s.minio_bucket_raw, object_key)
    try:
        get_minio().remove_object(s.minio_bucket_raw, object_key)
        log.info("[3/4] MinIO DELETE FIN — objet retiré")
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
            log.info("[3/4] MinIO DELETE FIN — déjà absent (%s)", exc.code)
            return
        raise


def _delete_qdrant(document_id: UUID) -> None:
    s = get_settings()
    log.info("[1/4] Qdrant DELETE DÉBUT collection=%s document_id=%s", s.qdrant_collection, document_id)
    client = QdrantClient(url=s.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        log.info("[1/4] Qdrant DELETE FIN — collection absente")
        return
    client.delete(
        collection_name=s.qdrant_collection,
        points_selector=Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=str(document_id))),
            ]
        ),
    )
    log.info("[1/4] Qdrant DELETE FIN — points du document retirés")


def _delete_neo4j(*, tenant_id: UUID, chunk_ids: list[str]) -> None:
    log.info("[2/4] Neo4j DELETE DÉBUT chunks=%s tenant=%s", len(chunk_ids), tenant_id)
    driver = _driver()
    try:
        with driver.session() as neo:
            rels = 0
            if chunk_ids:
                rec = neo.run(
                    "MATCH ()-[r:REL]->() WHERE r.source_chunk_id IN $ids RETURN count(r) AS n",
                    ids=chunk_ids,
                ).single()
                rels = int(rec["n"]) if rec else 0
                neo.run(
                    "MATCH ()-[r:REL]->() WHERE r.source_chunk_id IN $ids DELETE r",
                    ids=chunk_ids,
                )
            rec = neo.run(
                "MATCH (e:Entity {tenant_id: $tenant_id}) "
                "WHERE NOT (e)--() RETURN count(e) AS n",
                tenant_id=str(tenant_id),
            ).single()
            ents = int(rec["n"]) if rec else 0
            neo.run(
                "MATCH (e:Entity {tenant_id: $tenant_id}) "
                "WHERE NOT (e)--() DELETE e",
                tenant_id=str(tenant_id),
            )
        log.info("[2/4] Neo4j DELETE FIN — relations=%s entités orphelines=%s", rels, ents)
    finally:
        driver.close()


async def purge_document(session: AsyncSession, doc: Document) -> None:
    chunk_ids = [
        str(cid)
        for cid in (
            await session.execute(select(ChunkRow.id).where(ChunkRow.document_id == doc.id))
        ).scalars().all()
    ]
    log.info(
        "======== PURGE DÉBUT id=%s fichier=%s chunks=%s key=%s ========",
        doc.id,
        doc.filename,
        len(chunk_ids),
        doc.object_key,
    )
    _delete_qdrant(doc.id)
    _delete_neo4j(tenant_id=doc.tenant_id, chunk_ids=chunk_ids)
    _delete_minio(doc.object_key)
    log.info("[4/4] Postgres DELETE DÉBUT id=%s (chunks puis document)", doc.id)
    # Enfants d’abord (parent_id), puis parents — évite SET NULL ORM / NOT NULL.
    doc_id = doc.id
    await session.execute(
        delete(ChunkRow).where(ChunkRow.document_id == doc_id, ChunkRow.parent_id.is_not(None))
    )
    await session.execute(delete(ChunkRow).where(ChunkRow.document_id == doc_id))
    await session.execute(delete(Document).where(Document.id == doc_id))
    await session.commit()
    log.info("[4/4] Postgres DELETE FIN — ======== PURGE TERMINÉE id=%s ========", doc_id)

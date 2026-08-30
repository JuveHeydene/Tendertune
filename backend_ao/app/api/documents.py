"""Upload MinIO + listing documents + file d'ingestion."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.sql import Document, User
from app.services.db_client import get_session
from app.services.purge_document import can_delete_document, purge_document
from app.services.document_upload import store_document

log = logging.getLogger("btp.upload")

router = APIRouter(prefix="/documents", tags=["documents"])

DOC_ROLES = ("patrimoine", "dao_courant", "dao_archive", "annexe")
DOC_TYPES = ("rc", "cctp", "ccap", "memoire", "reference", "dpgf", "bpu", "administratif", "autre")


class DocumentOut(BaseModel):
    id: UUID
    tenant_id: UUID
    created_by: UUID | None
    filename: str
    doc_role: str
    doc_type: str | None
    is_dao: bool
    dossier_origine_id: UUID | None
    dossier_id: UUID | None = None
    status: str
    graph_extracted: bool
    ingest_error: str | None
    object_key: str
    sha: str
    size_bytes: int | None
    mime_type: str | None
    ocr_used: bool
    ocr_confidence: float | None
    page_count: int | None
    archived_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    duplicate: bool = False


def _out(d: Document, *, duplicate: bool = False) -> DocumentOut:
    return DocumentOut(
        id=d.id,
        tenant_id=d.tenant_id,
        created_by=d.created_by,
        filename=d.filename,
        doc_role=d.doc_role,
        doc_type=d.doc_type,
        is_dao=d.is_dao,
        dossier_origine_id=d.dossier_origine_id,
        dossier_id=d.dossier_id,
        status=d.status,
        graph_extracted=d.graph_extracted,
        ingest_error=d.ingest_error,
        object_key=d.object_key,
        sha=d.sha,
        size_bytes=d.size_bytes,
        mime_type=d.mime_type,
        ocr_used=d.ocr_used,
        ocr_confidence=d.ocr_confidence,
        page_count=d.page_count,
        archived_at=d.archived_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
        duplicate=duplicate,
    )


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    dossier_id: UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """`dossier_id` : filtre optionnel — utilisé par l'onglet "Documents" de
    la page dossier (annexes scopées, §3.2/§3.7)."""
    stmt = select(Document).where(Document.tenant_id == user.tenant_id)
    if dossier_id is not None:
        stmt = stmt.where(Document.dossier_id == dossier_id)
    rows = (await session.execute(stmt.order_by(Document.created_at.desc()))).scalars().all()
    return [_out(d) for d in rows]


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    doc_role: str = Form("patrimoine"),
    doc_type: str | None = Form(None),
    dossier_id: UUID | None = Form(None),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if doc_role not in DOC_ROLES:
        raise HTTPException(status_code=400, detail="doc_role invalide")
    if doc_type and doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="doc_type invalide")
    if doc_role == "annexe" and dossier_id is None:
        raise HTTPException(status_code=400, detail="doc_role='annexe' nécessite dossier_id (§1.5)")
    if user.role == "consultant":
        raise HTTPException(status_code=403, detail="Le consultant ne dépose pas de pièces")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    log.info(
        "UPLOAD start user=%s fichier=%s octets=%s rôle=%s type=%s mime=%s dossier=%s",
        user.email,
        file.filename,
        len(data),
        doc_role,
        doc_type,
        file.content_type,
        dossier_id,
    )
    filename = file.filename or "document.bin"
    doc, duplicate = await store_document(
        session,
        user,
        data,
        filename,
        doc_role=doc_role,
        doc_type=doc_type,
        content_type=file.content_type,
        dossier_id=dossier_id if doc_role == "annexe" else None,
    )
    if duplicate:
        log.info("UPLOAD doublon id=%s statut=%s", doc.id, doc.status)
        return _out(doc, duplicate=True)
    await session.commit()
    await session.refresh(doc)
    log.info("[2/4] Postgres INSERT FIN id=%s statut=%s sha=%s", doc.id, doc.status, doc.sha[:12])
    return _out(doc)


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return _out(doc)


@router.post("/{document_id}/promouvoir", response_model=DocumentOut)
async def promouvoir_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """§1.5 — promotion annexe → patrimoine. Réutilise `dossier_origine_id`,
    déjà prévu en V1 pour exactement ce rôle (provenance historique)."""
    if user.role == "consultant":
        raise HTTPException(status_code=403, detail="Action réservée au rédacteur, manager ou admin")
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.doc_role != "annexe":
        raise HTTPException(status_code=400, detail="Seule une annexe peut être promue")
    doc.doc_role = "patrimoine"
    doc.dossier_origine_id = doc.dossier_id
    doc.dossier_id = None
    await session.commit()
    await session.refresh(doc)
    if not doc.graph_extracted:
        from app.services.queue import get_queue

        redis = await get_queue()
        await redis.enqueue_job("extract_graph", str(doc.id))
    return _out(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not can_delete_document(user):
        raise HTTPException(
            status_code=403,
            detail="Seul un manager ou un admin peut supprimer un document",
        )
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    log.info("DELETE demandé par %s rôle=%s id=%s fichier=%s", user.email, user.role, doc.id, doc.filename)
    try:
        await purge_document(session, doc)
    except Exception as exc:
        await session.rollback()
        log.exception("DELETE ÉCHEC id=%s : %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Suppression incomplète : {exc}") from exc


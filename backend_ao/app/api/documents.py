"""Upload MinIO + listing documents + file d'ingestion."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.sql import Document, Dossier, User
from app.services.audit import record_audit
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
    # {"parse": {"started_at": .., "finished_at": .., "error": ..}, "chunk": {...},
    #  "classify": {...}, "embed": {...}, "index": {...}, "graph": {...}}
    pipeline_stages: dict = {}
    # Nombre de pages déjà OCRisées (reprise) — permet d'afficher une
    # progression pendant un scan encore en cours ou interrompu.
    ocr_pages_done: int = 0


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
        pipeline_stages=d.pipeline_stages or {},
        ocr_pages_done=len((d.ocr_progress or {}).get("pages") or {}),
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

    dossier: Dossier | None = None
    if doc_role in ("dao_courant", "dao_archive") and dossier_id is not None:
        dossier = await session.get(Dossier, dossier_id)
        if dossier is None or dossier.tenant_id != user.tenant_id:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

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
    if dossier is not None:
        # Lien Dossier → DAO courant : c'est le seul endroit qui l'établit —
        # sans lui, `analyser_dossier` (extraction exigences/outline, §9) ne
        # trouve jamais de document à lire.
        dossier.dao_document_id = doc.id
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


@router.post("/{document_id}/relancer-ingestion", response_model=DocumentOut)
async def relancer_ingestion(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Relance l'ingestion (lecture/OCR → découpage → classification →
    indexation) d'un document `failed`, ou resté bloqué en `processing`
    (ex. worker interrompu). Reprend depuis la dernière page OCR déjà
    persistée (`ocr_progress`) plutôt que de tout refaire — voir
    app/ingest/parse.py. Les anciens vecteurs sont purgés avant réindexation
    (app/ingest/index_qdrant.delete_by_document) : aucun résidu dupliqué."""
    if user.role == "consultant":
        raise HTTPException(status_code=403, detail="Action réservée au rédacteur, manager ou admin")
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Une ingestion est déjà en cours pour ce document — patientez qu'elle se termine.",
        )
    from app.services.queue import enqueue_ingest

    doc.status = "pending"
    doc.ingest_error = None
    await session.commit()
    await enqueue_ingest(str(doc.id))
    await session.refresh(doc)
    log.info("RELANCE ingestion demandée par %s id=%s (reprise depuis %s pages connues)",
             user.email, doc.id, len((doc.ocr_progress or {}).get("pages") or {}))
    return _out(doc)


@router.post("/{document_id}/relancer-graphe", response_model=DocumentOut)
async def relancer_graphe(
    document_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Relance UNIQUEMENT l'extraction du graphe (sans refaire le parse/
    chunking/embeddings) — pour un document déjà `ready` dont le graphe n'a
    jamais été extrait ou a échoué. Sûr à rejouer : écriture par MERGE sur
    des clés canoniques (app/graph/extract.py), jamais de doublon d'entité."""
    if user.role == "consultant":
        raise HTTPException(status_code=403, detail="Action réservée au rédacteur, manager ou admin")
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    if doc.status != "ready":
        raise HTTPException(
            status_code=400,
            detail="Le document doit être entièrement ingéré (statut 'ready') avant d'extraire son graphe.",
        )
    if doc.graph_extracted:
        raise HTTPException(status_code=409, detail="Le graphe est déjà extrait pour ce document.")
    from app.services.queue import enqueue_graph

    await enqueue_graph(str(doc.id))
    log.info("RELANCE extraction graphe demandée par %s id=%s", user.email, doc.id)
    return _out(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID,
    request: Request,
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
    details = {"filename": doc.filename, "sha": doc.sha[:16] if doc.sha else None}
    try:
        # purge_document commite lui-même en interne (plusieurs DELETE sur
        # Postgres/Qdrant/Neo4j/MinIO) — l'audit est donc une écriture
        # séparée, APRÈS coup, dans les deux branches (succès ou échec).
        await purge_document(session, doc)
        await record_audit(
            session, tenant_id=user.tenant_id, user_id=user.id, action_type="delete",
            resource_type="document", resource_id=document_id, details=details,
            request=request, success=True,
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        await record_audit(
            session, tenant_id=user.tenant_id, user_id=user.id, action_type="delete",
            resource_type="document", resource_id=document_id, details=details,
            request=request, success=False, error_message=str(exc),
        )
        await session.commit()
        log.exception("DELETE ÉCHEC id=%s : %s", document_id, exc)
        raise HTTPException(status_code=500, detail=f"Suppression incomplète : {exc}") from exc


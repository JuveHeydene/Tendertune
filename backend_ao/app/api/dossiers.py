"""Workflow dossier V2 : détail, exigences, plan, pièces administratives,
revue HITL réelle, export. Comble le trou documenté dans
Nouvelle_Architecture/base_de_donnees_et_interface.md §2 (endpoints listés
comme "squelette" / "not_implemented")."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.models.pydantic import DecisionHumaine, ReviewAction
from app.models.sql import (
    Document,
    Dossier,
    DossierPiece,
    ExigenceRow,
    Export,
    Generation,
    OutlineItem,
    Review,
    User,
)
from app.services.db_client import get_session
from app.services.dossier_workflow import EXT, MIME, save_generation
from app.services.minio_client import get_minio
from app.services.ollama_llm import ollama_generate_json
from app.services.queue import enqueue_extract_structure
from app.workflow.agentic_pipeline import run_agentic_retrieval
from app.workflow.extract_structure import cover_exigence
from app.workflow.nodes.aggregate import AggregatedContext
from app.workflow.nodes.generate_section import generate_section, section_to_markdown

log = logging.getLogger("btp.api.dossiers")

router = APIRouter(prefix="/dossiers", tags=["dossiers"])

WRITE_ROLES = {"admin", "manager", "redacteur"}


def _require_write(user: User) -> None:
    if user.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Action réservée au rédacteur, manager ou admin")


async def _get_owned_dossier(session: AsyncSession, dossier_id: UUID, user: User) -> Dossier:
    doss = await session.get(Dossier, dossier_id)
    if doss is None or doss.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return doss


class DossierOut(BaseModel):
    id: UUID
    client_name: str | None
    project_name: str | None
    dao_reference: str | None
    status: str
    deadline: str | None
    current_version: int | None = None
    exigences_total: int = 0
    exigences_couvertes: int = 0
    exigences_eliminatoires_non_couvertes: int = 0
    sections_total: int = 0
    sections_approuvees: int = 0


@router.get("", response_model=list[DossierOut])
async def list_dossiers(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """§3.1 — enrichi des indicateurs de couverture/avancement (plus une
    simple liste plate)."""
    rows = (
        await session.execute(
            select(Dossier).where(Dossier.tenant_id == user.tenant_id).order_by(Dossier.updated_at.desc())
        )
    ).scalars().all()
    out: list[DossierOut] = []
    for d in rows:
        exigences = (await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == d.id))).scalars().all()
        outline = (await session.execute(select(OutlineItem).where(OutlineItem.dossier_id == d.id))).scalars().all()
        out.append(
            DossierOut(
                id=d.id,
                client_name=d.client_name,
                project_name=d.project_name,
                dao_reference=d.dao_reference,
                status=d.status,
                deadline=d.deadline.isoformat() if d.deadline else None,
                current_version=d.current_version,
                exigences_total=len(exigences),
                exigences_couvertes=sum(1 for e in exigences if e.statut == "couverte"),
                exigences_eliminatoires_non_couvertes=sum(
                    1 for e in exigences if e.obligatoire and e.statut == "non_couverte"
                ),
                sections_total=len(outline),
                sections_approuvees=sum(1 for o in outline if o.status == "approved"),
            )
        )
    return out


@router.get("/{dossier_id}", response_model=DossierOut)
async def get_dossier(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    exigences = (await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == doss.id))).scalars().all()
    outline = (await session.execute(select(OutlineItem).where(OutlineItem.dossier_id == doss.id))).scalars().all()
    return DossierOut(
        id=doss.id, client_name=doss.client_name, project_name=doss.project_name,
        dao_reference=doss.dao_reference, status=doss.status,
        deadline=doss.deadline.isoformat() if doss.deadline else None,
        current_version=doss.current_version,
        exigences_total=len(exigences),
        exigences_couvertes=sum(1 for e in exigences if e.statut == "couverte"),
        exigences_eliminatoires_non_couvertes=sum(1 for e in exigences if e.obligatoire and e.statut == "non_couverte"),
        sections_total=len(outline),
        sections_approuvees=sum(1 for o in outline if o.status == "approved"),
    )


@router.post("/{dossier_id}/analyser")
async def analyser_dossier(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """§9 — déclenche extract_dossier_structure (outline + exigences +
    checklist administrative). Déterministe, asynchrone (job ARQ)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    if not doss.dao_document_id:
        raise HTTPException(status_code=400, detail="Ce dossier n'a pas de DAO courant à analyser")
    job_id = await enqueue_extract_structure(str(doss.id))
    return {"dossier_id": str(doss.id), "status": "analyzing", "job_id": job_id}


# ---------------------------------------------------------------------------
# Exigences (§3.3)
# ---------------------------------------------------------------------------


class ExigenceOut(BaseModel):
    id: UUID
    libelle: str
    type: str
    obligatoire: bool
    statut: str
    reference_dao: str | None
    page_source: int | None
    preuves_chunks: list = []


@router.get("/{dossier_id}/exigences", response_model=list[ExigenceOut])
async def list_exigences(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    rows = (
        await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == doss.id).order_by(ExigenceRow.created_at))
    ).scalars().all()
    return [
        ExigenceOut(
            id=e.id, libelle=e.libelle, type=e.type, obligatoire=e.obligatoire, statut=e.statut,
            reference_dao=e.reference_dao, page_source=e.page_source, preuves_chunks=e.preuves_chunks or [],
        )
        for e in rows
    ]


@router.post("/{dossier_id}/exigences/{exigence_id}/recherche")
async def relancer_recherche_exigence(
    dossier_id: UUID,
    exigence_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """§3.3 — bouton "Relancer la recherche". Réutilise le CRAG existant
    (app.rag.experts), aucune nouvelle mécanique de retrieval."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    exigence = await session.get(ExigenceRow, exigence_id)
    if exigence is None or exigence.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Exigence introuvable")
    background_tasks.add_task(cover_exigence, exigence.id, tenant_id=user.tenant_id)
    return {"exigence_id": str(exigence.id), "status": "en_cours"}


# ---------------------------------------------------------------------------
# Plan / outline (§3.4)
# ---------------------------------------------------------------------------


class OutlineItemOut(BaseModel):
    id: UUID
    key: str
    title: str
    heading_level: int
    sort_order: int
    status: str
    archetype: str


@router.get("/{dossier_id}/outline", response_model=list[OutlineItemOut])
async def list_outline(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    rows = (
        await session.execute(select(OutlineItem).where(OutlineItem.dossier_id == doss.id).order_by(OutlineItem.sort_order))
    ).scalars().all()
    return [
        OutlineItemOut(
            id=o.id, key=o.key, title=o.title, heading_level=o.heading_level,
            sort_order=o.sort_order, status=o.status, archetype=o.archetype,
        )
        for o in rows
    ]


# ---------------------------------------------------------------------------
# Sections — génération + revue HITL réelle (§3.5)
# ---------------------------------------------------------------------------


class SectionDetailOut(BaseModel):
    section_key: str
    title: str
    status: str
    version: int | None = None
    markdown: str | None = None
    citations: list = []
    abstentions: list = []
    exigences_couvertes: list = []


@router.get("/{dossier_id}/sections/{section_key}", response_model=SectionDetailOut)
async def get_section(
    dossier_id: UUID,
    section_key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == doss.id, OutlineItem.key == section_key)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Section introuvable")
    gen = (
        await session.execute(
            select(Generation)
            .where(Generation.dossier_id == doss.id, Generation.section_key == section_key)
            .order_by(Generation.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    content = gen.content if gen else {}
    return SectionDetailOut(
        section_key=section_key, title=item.title, status=item.status,
        version=gen.version if gen else None,
        markdown=content.get("texte"),
        citations=gen.citations if gen else [],
        abstentions=content.get("abstentions", []),
        exigences_couvertes=gen.exigences_couvertes if gen else [],
    )


@router.post("/{dossier_id}/sections/{section_key}/generate", response_model=SectionDetailOut)
async def generate_section_endpoint(
    dossier_id: UUID,
    section_key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Génère (ou régénère) UNE section via le pipeline agentique complet."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == doss.id, OutlineItem.key == section_key)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Section introuvable dans le plan")

    _q, _sup, aggregated = await run_agentic_retrieval(
        f"Rédige la section : {item.title}", [],
        tenant_id=user.tenant_id, dossier_id=doss.id, message_id=None,
    )
    aggregated = aggregated or AggregatedContext(context_text="(aucun contexte)")
    section = await generate_section(
        section_key=section_key, titre=item.title, archetype=item.archetype,
        aggregated=aggregated, history=[],
    )
    markdown = section_to_markdown(section)
    gen = await save_generation(
        session, dossier=doss, section_key=section_key, title=item.title, texte=markdown,
        citations=section.citations, model=get_settings().llm_model,
        content={**section.model_dump(), "texte": markdown},
        context_snapshot={"extraits": aggregated.context_text[:20000]},
        exigences_couvertes=section.exigences_couvertes,
    )
    return SectionDetailOut(
        section_key=section_key, title=item.title, status="generated", version=gen.version,
        markdown=markdown, citations=section.citations, abstentions=section.abstentions,
        exigences_couvertes=section.exigences_couvertes,
    )


@router.post("/{dossier_id}/sections/{section_key}/review")
async def review_section(
    dossier_id: UUID,
    section_key: str,
    body: ReviewAction,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """HITL réel — approve / edit / regen (remplace le stub not_implemented)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == doss.id, OutlineItem.key == section_key)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Section introuvable")
    gen = (
        await session.execute(
            select(Generation)
            .where(Generation.dossier_id == doss.id, Generation.section_key == section_key)
            .order_by(Generation.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if gen is None:
        raise HTTPException(status_code=400, detail="Aucune génération à revoir — générez d'abord la section")

    if body.action == DecisionHumaine.approve:
        item.status = "approved"
        item.updated_at = datetime.now(UTC)
        # §2.3 — résumé de progression PRÉCALCULÉ ici, jamais recalculé à
        # chaque question de chat.
        try:
            summary_prompt = (
                "Résume en UNE phrase courte le contenu de cette section pour "
                "un mémoire technique BTP (utile pour donner du contexte à "
                "d'autres sections) : \n\n" + (gen.content or {}).get("texte", "")[:3000]
            )
            body_json = ollama_generate_json(
                summary_prompt + '\nRéponds UNIQUEMENT en JSON : {"resume": "..."}', timeout=60
            )
            gen.summary_short = str(body_json.get("resume") or "").strip() or None
        except Exception as exc:
            log.warning("review_section — résumé de dossier non généré : %s", exc)
        session.add(Review(generation_id=gen.id, user_id=user.id, action="approve", comment=body.comment))
    elif body.action == DecisionHumaine.edit:
        item.status = "approved"
        item.updated_at = datetime.now(UTC)
        content = {**(gen.content or {}), "texte": body.text or ""}
        new_gen = await save_generation(
            session, dossier=doss, section_key=section_key, title=item.title,
            texte=body.text or "", citations=gen.citations, model=gen.model or get_settings().llm_model,
            content=content,
        )
        session.add(Review(generation_id=new_gen.id, user_id=user.id, action="edit", modified_text=body.text, comment=body.comment))
    elif body.action == DecisionHumaine.regen:
        item.status = "rejected"
        item.updated_at = datetime.now(UTC)
        session.add(
            Review(generation_id=gen.id, user_id=user.id, action="regen", regen_instruction=body.comment, comment=body.comment)
        )
        _q, _sup, aggregated = await run_agentic_retrieval(
            f"Rédige la section : {item.title}", [],
            tenant_id=user.tenant_id, dossier_id=doss.id, message_id=None,
        )
        aggregated = aggregated or AggregatedContext(context_text="(aucun contexte)")
        section = await generate_section(
            section_key=section_key, titre=item.title, archetype=item.archetype,
            aggregated=aggregated, history=[], custom_instruction=body.comment,
        )
        markdown = section_to_markdown(section)
        new_gen = await save_generation(
            session, dossier=doss, section_key=section_key, title=item.title, texte=markdown,
            citations=section.citations, model=get_settings().llm_model,
            content={**section.model_dump(), "texte": markdown},
            exigences_couvertes=section.exigences_couvertes,
        )
        item.status = "generated"
    await session.commit()
    return {"dossier_id": str(doss.id), "section_key": section_key, "action": body.action, "status": item.status}


# ---------------------------------------------------------------------------
# Pièces administratives (§5.3)
# ---------------------------------------------------------------------------


class DossierPieceOut(BaseModel):
    id: UUID
    libelle: str
    obligatoire: bool
    statut: str
    document_id: UUID | None
    source: str


@router.get("/{dossier_id}/pieces", response_model=list[DossierPieceOut])
async def list_pieces(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    rows = (
        await session.execute(select(DossierPiece).where(DossierPiece.dossier_id == doss.id))
    ).scalars().all()
    return [
        DossierPieceOut(id=p.id, libelle=p.libelle, obligatoire=p.obligatoire, statut=p.statut, document_id=p.document_id, source=p.source)
        for p in rows
    ]


class ChoisirPieceIn(BaseModel):
    document_id: UUID


@router.post("/{dossier_id}/pieces/{piece_id}/choisir")
async def choisir_piece(
    dossier_id: UUID,
    piece_id: UUID,
    body: ChoisirPieceIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    piece = await session.get(DossierPiece, piece_id)
    if piece is None or piece.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Pièce introuvable")
    doc = await session.get(Document, body.document_id)
    if doc is None or doc.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Document introuvable")
    piece.document_id = doc.id
    piece.statut = "fourni"
    piece.updated_at = datetime.now(UTC)
    await session.commit()
    return {"piece_id": str(piece.id), "statut": piece.statut}


# ---------------------------------------------------------------------------
# Export (inchangé)
# ---------------------------------------------------------------------------


@router.get("/{dossier_id}/export.{fmt}")
async def download_export(
    dossier_id: UUID,
    fmt: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if fmt not in EXT:
        raise HTTPException(status_code=400, detail=f"Format {fmt!r} invalide")
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    rec = (
        await session.execute(
            select(Export).where(Export.dossier_id == doss.id, Export.format == fmt).order_by(Export.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=404, detail="Aucun export pour ce format. Utilisez Exporter le document en conversation.")
    settings = get_settings()
    response = None
    try:
        response = get_minio().get_object(settings.minio_bucket_export, rec.object_key)
        data = response.read()
    finally:
        if response is not None:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass
    base = (doss.project_name or str(doss.id)).replace(" ", "_")
    filename = f"memoire-{base}-v{rec.version}.{EXT[fmt]}"
    return StreamingResponse(
        BytesIO(data), media_type=MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

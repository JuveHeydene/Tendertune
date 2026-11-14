"""Workflow dossier V2 : détail, exigences, plan, pièces administratives,
revue HITL réelle, export. Comble le trou documenté dans
Nouvelle_Architecture/base_de_donnees_et_interface.md §2 (endpoints listés
comme "squelette" / "not_implemented")."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.models.pydantic import DecisionHumaine, ReviewAction
from app.models.sql import (
    ChunkRow,
    Document,
    Dossier,
    DossierPiece,
    ExigenceRow,
    ExigenceSection,
    Export,
    Generation,
    OutlineItem,
    RetrievalTrace,
    Review,
    User,
)
from app.services.db_client import get_session
from app.services.document_upload import store_document
from app.services.dossier_workflow import EXT, MIME, active_exigences_for_section, save_generation
from app.services.minio_client import get_minio
from app.services.ollama_llm import ollama_generate_json
from app.services.pieces_export import build_pieces_pdf
from app.services.queue import enqueue_classify_sections, enqueue_extract_structure
from app.workflow.agentic_pipeline import run_agentic_retrieval
from app.workflow.extract_structure import cover_exigence
from app.workflow.nodes.aggregate import AggregatedContext
from app.workflow.nodes.generate_section import generate_section, section_to_markdown
from app.workflow.nodes.route import is_proposal_request

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


async def _dao_fields(session: AsyncSession, dao_document_id: UUID | None) -> dict:
    if dao_document_id is None:
        return {"dao_filename": None, "dao_status": None, "dao_ingest_error": None}
    doc = await session.get(Document, dao_document_id)
    if doc is None:
        return {"dao_filename": None, "dao_status": None, "dao_ingest_error": None}
    return {"dao_filename": doc.filename, "dao_status": doc.status, "dao_ingest_error": doc.ingest_error}


class DossierOut(BaseModel):
    id: UUID
    client_name: str | None
    project_name: str | None
    dao_reference: str | None
    status: str
    deadline: str | None
    current_version: int | None = None
    has_dao: bool = False
    dao_document_id: UUID | None = None
    dao_filename: str | None = None
    # Statut d'INGESTION du DAO (pending/processing/ready/failed), pas le
    # statut du dossier — un scan PDF passe par PaddleOCR (app/ingest/parse.py
    # _parse_pdf) et peut rester "processing" plusieurs minutes. `analyser`
    # doit attendre "ready", sinon extract_outline/extract_exigences lisent
    # 0 chunk et retombent silencieusement sur le plan générique (§9).
    dao_status: str | None = None
    dao_ingest_error: str | None = None
    exigences_total: int = 0
    exigences_couvertes: int = 0
    exigences_eliminatoires_non_couvertes: int = 0
    sections_total: int = 0
    sections_approuvees: int = 0
    # Suivi du job "classifier les exigences par section" — null/running/
    # ready/failed (jamais lancé/en cours/dernier passage ok/dernier échec).
    classification_status: str | None = None
    classification_error: str | None = None


class DossierCreate(BaseModel):
    project_name: str
    client_name: str | None = None
    dao_reference: str | None = None
    deadline: str | None = None


class DossierUpdate(BaseModel):
    project_name: str | None = None
    client_name: str | None = None
    dao_reference: str | None = None
    deadline: str | None = None


async def _to_dossier_out(session: AsyncSession, doss: Dossier) -> DossierOut:
    exigences = (await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == doss.id))).scalars().all()
    outline = (await session.execute(select(OutlineItem).where(OutlineItem.dossier_id == doss.id))).scalars().all()
    dao = await _dao_fields(session, doss.dao_document_id)
    return DossierOut(
        id=doss.id, client_name=doss.client_name, project_name=doss.project_name,
        dao_reference=doss.dao_reference, status=doss.status,
        deadline=doss.deadline.isoformat() if doss.deadline else None,
        current_version=doss.current_version,
        has_dao=doss.dao_document_id is not None,
        dao_document_id=doss.dao_document_id,
        **dao,
        exigences_total=len(exigences),
        exigences_couvertes=sum(1 for e in exigences if e.statut == "couverte"),
        exigences_eliminatoires_non_couvertes=sum(1 for e in exigences if e.obligatoire and e.statut == "non_couverte"),
        sections_total=len(outline),
        sections_approuvees=sum(1 for o in outline if o.status == "approved"),
        classification_status=doss.classification_status,
        classification_error=doss.classification_error,
    )


def _parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Échéance invalide (format ISO attendu)") from exc


@router.post("", response_model=DossierOut, status_code=201)
async def create_dossier(
    body: DossierCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Création indépendante d'un dossier — un dossier existe AVANT toute
    conversation, exigence ou section. Aucun outline n'est inséré ici : le
    plan réel vient uniquement de `analyser_dossier` une fois le DAO chargé
    (§9). Corrige l'inversion documentée dans Nouvelle_Architecture :
    auparavant un dossier n'existait qu'en sous-produit lazy d'une
    conversation, avec un outline générique, avant même qu'un DAO soit lu."""
    _require_write(user)
    if not body.project_name.strip():
        raise HTTPException(status_code=400, detail="Le nom du projet est requis")
    doss = Dossier(
        tenant_id=user.tenant_id,
        created_by=user.id,
        project_name=body.project_name.strip(),
        client_name=body.client_name.strip() if body.client_name else None,
        dao_reference=body.dao_reference.strip() if body.dao_reference else None,
        deadline=_parse_deadline(body.deadline),
        status="draft",
    )
    session.add(doss)
    await session.commit()
    await session.refresh(doss)
    return await _to_dossier_out(session, doss)


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
    return [await _to_dossier_out(session, d) for d in rows]


@router.get("/{dossier_id}", response_model=DossierOut)
async def get_dossier(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    return await _to_dossier_out(session, doss)


@router.patch("/{dossier_id}", response_model=DossierOut)
async def update_dossier(
    dossier_id: UUID,
    body: DossierUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Modification des informations d'un dossier (nom, client, réf. DAO,
    échéance) — jusqu'ici impossible : un dossier ne pouvait être renommé
    après sa création."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    if body.project_name is not None:
        if not body.project_name.strip():
            raise HTTPException(status_code=400, detail="Le nom du projet est requis")
        doss.project_name = body.project_name.strip()
    if body.client_name is not None:
        doss.client_name = body.client_name.strip() or None
    if body.dao_reference is not None:
        doss.dao_reference = body.dao_reference.strip() or None
    if body.deadline is not None:
        doss.deadline = _parse_deadline(body.deadline) if body.deadline.strip() else None
    doss.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(doss)
    return await _to_dossier_out(session, doss)


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
    if doss.status == "analyzing":
        # Évite deux jobs extract_dossier_structure concurrents sur le même
        # dossier (observé : un double-clic ou deux appels rapprochés
        # produisent des exigences en double, sans contrainte d'unicité pour
        # s'en protéger côté base).
        raise HTTPException(
            status_code=409,
            detail="Une analyse est déjà en cours pour ce dossier — patientez qu'elle se termine.",
        )
    if not doss.dao_document_id:
        raise HTTPException(status_code=400, detail="Ce dossier n'a pas de DAO courant à analyser")
    dao_doc = await session.get(Document, doss.dao_document_id)
    if dao_doc is None:
        raise HTTPException(status_code=400, detail="Le DAO référencé est introuvable")
    if dao_doc.status == "failed":
        raise HTTPException(
            status_code=400,
            detail=f"La lecture du DAO a échoué ({dao_doc.ingest_error or 'erreur inconnue'}). "
            "Rechargez le fichier dans l'onglet Documents.",
        )
    if dao_doc.status != "ready":
        # Un PDF scanné passe par PaddleOCR (app/ingest/parse.py) — plus long
        # qu'un PDF texte natif. Lancer l'analyse avant la fin de l'OCR ferait
        # lire 0 chunk à extract_outline/extract_exigences, qui retomberaient
        # silencieusement sur le plan générique (régression du problème §9
        # qu'on vient de corriger).
        raise HTTPException(
            status_code=409,
            detail="Le DAO est encore en cours de lecture (OCR pour un scan, extraction pour un PDF "
            "texte) — patientez avant de lancer l'analyse.",
        )
    doss.status = "analyzing"
    await session.commit()
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


@router.post("/{dossier_id}/exigences/classifier-sections")
async def classifier_exigences_sections(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Déclenche la classification LLM exigence -> section(s) (onglet
    Sections). Job ARQ séparé de `analyser` — rejouable à tout moment (ex.
    après ajout manuel d'exigences) sans retoucher outline/exigences déjà
    extraits. Les liens déjà confirmés/exclus par un humain ne sont jamais
    réécrits (ON CONFLICT DO NOTHING, voir classify_exigences_sections)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    if doss.classification_status == "running":
        raise HTTPException(
            status_code=409,
            detail="Une classification est déjà en cours pour ce dossier — patientez qu'elle se termine.",
        )
    n_exigences = (
        await session.execute(select(ExigenceRow.id).where(ExigenceRow.dossier_id == doss.id))
    ).scalars().all()
    n_sections = (
        await session.execute(select(OutlineItem.id).where(OutlineItem.dossier_id == doss.id))
    ).scalars().all()
    if not n_exigences or not n_sections:
        raise HTTPException(
            status_code=400,
            detail="Il faut au moins une exigence et une section (lancez « Analyser le DAO » d'abord).",
        )
    doss.classification_status = "running"
    doss.classification_error = None
    await session.commit()
    job_id = await enqueue_classify_sections(str(doss.id))
    return {"dossier_id": str(doss.id), "status": "running", "job_id": job_id}


class ExigencePreuveOut(BaseModel):
    chunk_id: str
    document_id: UUID | None
    document_filename: str | None
    page: int | None
    heading_path: str | None
    text: str


@router.get("/{dossier_id}/exigences/{exigence_id}/preuves", response_model=list[ExigencePreuveOut])
async def get_exigence_preuves(
    dossier_id: UUID,
    exigence_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Résout les ids stockés dans `preuves_chunks` en contenu lisible —
    sans ça, un statut "couverte" est une boîte noire : impossible de savoir
    QUEL document a été jugé pertinent ni de vérifier si la décision
    automatique du CRAG est correcte."""
    doss = await _get_owned_dossier(session, dossier_id, user)
    exigence = await session.get(ExigenceRow, exigence_id)
    if exigence is None or exigence.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Exigence introuvable")
    chunk_ids = exigence.preuves_chunks or []
    if not chunk_ids:
        return []
    try:
        uuids = [UUID(str(cid)) for cid in chunk_ids]
    except ValueError:
        return []
    rows = (
        await session.execute(
            select(ChunkRow, Document.filename)
            .join(Document, Document.id == ChunkRow.document_id)
            .where(ChunkRow.id.in_(uuids))
        )
    ).all()
    by_id = {str(chunk.id): (chunk, filename) for chunk, filename in rows}
    # On restitue l'ORDRE de preuves_chunks (les 5 meilleurs résultats du
    # rerank, du plus au moins pertinent) — pas l'ordre arbitraire du SELECT.
    out: list[ExigencePreuveOut] = []
    for cid in chunk_ids:
        found = by_id.get(str(cid))
        if found is None:
            continue
        chunk, filename = found
        out.append(
            ExigencePreuveOut(
                chunk_id=str(chunk.id),
                document_id=chunk.document_id,
                document_filename=filename,
                page=chunk.page,
                heading_path=chunk.heading_path,
                text=chunk.text,
            )
        )
    return out


@router.post("/{dossier_id}/exigences/{exigence_id}/recherche")
async def relancer_recherche_exigence(
    dossier_id: UUID,
    exigence_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """§3.3 — bouton "Relancer la recherche". Réutilise le CRAG existant
    (app.rag.experts), aucune nouvelle mécanique de retrieval.

    Le passage à `statut="en_cours"` est fait ICI, de façon synchrone, AVANT
    de planifier la tâche de fond — pas dans `cover_exigence` lui-même. La
    recherche CRAG peut prendre plusieurs secondes (jusqu'à 3 itérations
    LLM) ; si on attendait que `cover_exigence` pose "en_cours", un second
    clic pendant ce délai voyait encore l'ancien statut et déclenchait une
    seconde recherche concurrente sur la même exigence (bug observé)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    exigence = await session.get(ExigenceRow, exigence_id)
    if exigence is None or exigence.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Exigence introuvable")
    if exigence.statut == "en_cours":
        raise HTTPException(status_code=409, detail="Une recherche est déjà en cours pour cette exigence.")
    exigence.statut = "en_cours"
    exigence.updated_at = datetime.now(UTC)
    await session.commit()
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


class RetrievalTraceOut(BaseModel):
    sous_question_index: int
    sous_question_texte: str | None
    expert: str
    tentative: int
    query_utilisee: str
    filtres: dict
    grade: str | None
    grade_method: str | None
    chunks_retournes: list
    abstention: bool
    created_at: datetime


@router.get("/{dossier_id}/sections/{section_key}/traces", response_model=list[RetrievalTraceOut])
async def get_section_traces(
    dossier_id: UUID,
    section_key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Explique POURQUOI la dernière génération de cette section a retenu
    tel contexte : chaque tentative CRAG (requête, filtres, note de
    grading, chunks retournés, abstention). `retrieval_traces` existait
    depuis le début (écrite dans app/rag/experts.py) mais n'était reliée à
    aucune génération ni consultable nulle part avant ce endpoint — voir
    `trace_batch_id` (migration 005) pour le mécanisme de corrélation."""
    doss = await _get_owned_dossier(session, dossier_id, user)
    gen = (
        await session.execute(
            select(Generation)
            .where(Generation.dossier_id == doss.id, Generation.section_key == section_key)
            .order_by(Generation.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if gen is None:
        raise HTTPException(status_code=404, detail="Aucune génération pour cette section")
    batch_id = (gen.context_snapshot or {}).get("trace_batch_id")
    if not batch_id:
        # Génération antérieure à cette fonctionnalité (§ traçabilité) —
        # rien à retrouver, pas une erreur.
        return []
    rows = (
        await session.execute(
            select(RetrievalTrace)
            .where(RetrievalTrace.trace_batch_id == UUID(batch_id))
            .order_by(RetrievalTrace.sous_question_index, RetrievalTrace.tentative)
        )
    ).scalars().all()
    return [
        RetrievalTraceOut(
            sous_question_index=t.sous_question_index, sous_question_texte=t.sous_question_texte,
            expert=t.expert, tentative=t.tentative, query_utilisee=t.query_utilisee, filtres=t.filtres or {},
            grade=t.grade, grade_method=t.grade_method, chunks_retournes=t.chunks_retournes or [],
            abstention=t.abstention, created_at=t.created_at,
        )
        for t in rows
    ]


async def _get_outline_item(session: AsyncSession, doss: Dossier, section_key: str) -> OutlineItem:
    item = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == doss.id, OutlineItem.key == section_key)
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Section introuvable")
    return item


class ExigenceSectionOut(BaseModel):
    exigence_id: UUID
    libelle: str
    type: str
    obligatoire: bool
    statut_couverture: str
    origine: str
    statut_lien: str
    preuves_chunks: list = []


@router.get("/{dossier_id}/sections/{section_key}/exigences", response_model=list[ExigenceSectionOut])
async def list_section_exigences(
    dossier_id: UUID,
    section_key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Exigences associées à cette section — proposées par la classification
    LLM et/ou confirmées/ajoutées à la main, jamais celles exclues. C'est
    cette liste (moins celles exclues) qui est injectée dans le prompt de
    generate_section() (§ pragmatisme patrimoine=exemple, pas copie)."""
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = await _get_outline_item(session, doss, section_key)
    rows = (
        await session.execute(
            select(ExigenceRow, ExigenceSection)
            .join(ExigenceSection, ExigenceSection.exigence_id == ExigenceRow.id)
            .where(ExigenceSection.outline_item_id == item.id, ExigenceSection.statut != "exclue")
            .order_by(ExigenceRow.obligatoire.desc(), ExigenceRow.created_at)
        )
    ).all()
    return [
        ExigenceSectionOut(
            exigence_id=ex.id, libelle=ex.libelle, type=ex.type, obligatoire=ex.obligatoire,
            statut_couverture=ex.statut, origine=link.origine, statut_lien=link.statut,
            preuves_chunks=ex.preuves_chunks or [],
        )
        for ex, link in rows
    ]


@router.post("/{dossier_id}/sections/{section_key}/exigences/{exigence_id}", response_model=ExigenceSectionOut)
async def link_section_exigence(
    dossier_id: UUID,
    section_key: str,
    exigence_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Associe manuellement une exigence à cette section — indépendant de la
    classification LLM, auto-confirmé (un humain qui ajoute a déjà décidé).
    Réactive aussi un lien LLM précédemment exclu."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = await _get_outline_item(session, doss, section_key)
    exigence = await session.get(ExigenceRow, exigence_id)
    if exigence is None or exigence.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Exigence introuvable")
    link = (
        await session.execute(
            select(ExigenceSection).where(
                ExigenceSection.exigence_id == exigence_id, ExigenceSection.outline_item_id == item.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        link = ExigenceSection(exigence_id=exigence_id, outline_item_id=item.id, origine="humain", statut="confirmee")
        session.add(link)
    else:
        link.statut = "confirmee"
    link.updated_at = datetime.now(UTC)
    await session.commit()
    return ExigenceSectionOut(
        exigence_id=exigence.id, libelle=exigence.libelle, type=exigence.type, obligatoire=exigence.obligatoire,
        statut_couverture=exigence.statut, origine=link.origine, statut_lien=link.statut,
    )


@router.post(
    "/{dossier_id}/sections/{section_key}/exigences/{exigence_id}/confirmer",
    response_model=ExigenceSectionOut,
)
async def confirm_section_exigence(
    dossier_id: UUID,
    section_key: str,
    exigence_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Confirme une proposition de la classification LLM — purement
    déclaratif pour la revue humaine : la liaison était déjà active pour le
    prompt dès sa proposition (voir list_section_exigences)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = await _get_outline_item(session, doss, section_key)
    link = (
        await session.execute(
            select(ExigenceSection).where(
                ExigenceSection.exigence_id == exigence_id, ExigenceSection.outline_item_id == item.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Aucun lien exigence/section à confirmer")
    link.statut = "confirmee"
    link.updated_at = datetime.now(UTC)
    await session.commit()
    exigence = await session.get(ExigenceRow, exigence_id)
    return ExigenceSectionOut(
        exigence_id=exigence.id, libelle=exigence.libelle, type=exigence.type, obligatoire=exigence.obligatoire,
        statut_couverture=exigence.statut, origine=link.origine, statut_lien=link.statut,
    )


@router.delete("/{dossier_id}/sections/{section_key}/exigences/{exigence_id}", status_code=204)
async def unlink_section_exigence(
    dossier_id: UUID,
    section_key: str,
    exigence_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retire une exigence de cette section. Une proposition LLM est
    marquée 'exclue' (conservée pour qu'une reclassification ultérieure ne
    la resuggère pas) ; un lien ajouté à la main est supprimé pour de bon
    (rien à retenir, il n'a jamais été auto-généré)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    item = await _get_outline_item(session, doss, section_key)
    link = (
        await session.execute(
            select(ExigenceSection).where(
                ExigenceSection.exigence_id == exigence_id, ExigenceSection.outline_item_id == item.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        return
    if link.origine == "llm":
        link.statut = "exclue"
        link.updated_at = datetime.now(UTC)
        await session.commit()
    else:
        await session.delete(link)
        await session.commit()


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

    trace_batch_id = uuid4()
    _q, _sup, aggregated = await run_agentic_retrieval(
        f"Rédige la section : {item.title}", [],
        tenant_id=user.tenant_id, dossier_id=doss.id, message_id=None,
        trace_batch_id=trace_batch_id,
    )
    aggregated = aggregated or AggregatedContext(context_text="(aucun contexte)")
    exigences = await active_exigences_for_section(session, item.id)
    section = await generate_section(
        section_key=section_key, titre=item.title, archetype=item.archetype,
        aggregated=aggregated, history=[], exigences=exigences,
    )
    markdown = section_to_markdown(section)
    gen = await save_generation(
        session, dossier=doss, section_key=section_key, title=item.title, texte=markdown,
        citations=section.citations, model=get_settings().llm_model,
        content={**section.model_dump(), "texte": markdown},
        # trace_batch_id : clé de corrélation vers retrieval_traces (§
        # traçabilité, migration 005) — voir GET .../sections/{key}/traces.
        context_snapshot={"extraits": aggregated.context_text[:20000], "trace_batch_id": str(trace_batch_id)},
        exigences_couvertes=section.exigences_couvertes,
    )
    await session.commit()
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
                summary_prompt + '\nRéponds UNIQUEMENT en JSON : {"resume": "..."}', timeout=60, num_ctx=2048
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
        trace_batch_id = uuid4()
        _q, _sup, aggregated = await run_agentic_retrieval(
            f"Rédige la section : {item.title}", [],
            tenant_id=user.tenant_id, dossier_id=doss.id, message_id=None,
            trace_batch_id=trace_batch_id,
        )
        aggregated = aggregated or AggregatedContext(context_text="(aucun contexte)")
        exigences = await active_exigences_for_section(session, item.id)
        section = await generate_section(
            section_key=section_key, titre=item.title, archetype=item.archetype,
            aggregated=aggregated, history=[], custom_instruction=body.comment, exigences=exigences,
            allow_proposal=bool(body.comment and is_proposal_request(body.comment)),
        )
        markdown = section_to_markdown(section)
        new_gen = await save_generation(
            session, dossier=doss, section_key=section_key, title=item.title, texte=markdown,
            citations=section.citations, model=get_settings().llm_model,
            content={**section.model_dump(), "texte": markdown},
            context_snapshot={"trace_batch_id": str(trace_batch_id)},
            exigences_couvertes=section.exigences_couvertes,
        )
        item.status = "generated"
    await session.commit()
    return {"dossier_id": str(doss.id), "section_key": section_key, "action": body.action, "status": item.status}


# ---------------------------------------------------------------------------
# Historique (§3.6) — reviews + versions
# ---------------------------------------------------------------------------


class ReviewOut(BaseModel):
    id: UUID
    version: int
    action: str
    comment: str | None
    created_at: str


@router.get("/{dossier_id}/sections/{section_key}/historique", response_model=list[ReviewOut])
async def section_historique(
    dossier_id: UUID,
    section_key: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    doss = await _get_owned_dossier(session, dossier_id, user)
    gens = (
        await session.execute(
            select(Generation)
            .where(Generation.dossier_id == doss.id, Generation.section_key == section_key)
            .order_by(Generation.version)
        )
    ).scalars().all()
    out: list[ReviewOut] = []
    for gen in gens:
        reviews = (
            await session.execute(select(Review).where(Review.generation_id == gen.id).order_by(Review.created_at))
        ).scalars().all()
        for r in reviews:
            out.append(
                ReviewOut(id=r.id, version=gen.version, action=r.action, comment=r.comment, created_at=r.created_at.isoformat())
            )
    return out


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


class PieceCreateIn(BaseModel):
    libelle: str = Field(min_length=2, max_length=255)
    obligatoire: bool = True


@router.post("/{dossier_id}/pieces", response_model=DossierPieceOut, status_code=201)
async def create_piece(
    dossier_id: UUID,
    body: PieceCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Ajoute une rubrique personnalisée à la checklist — pour une pièce
    dynamique non prévue par le RC ni la liste standard (§5.3)."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    libelle = body.libelle.strip()
    existing = (
        await session.execute(
            select(DossierPiece).where(DossierPiece.dossier_id == doss.id, DossierPiece.libelle == libelle)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Une pièce porte déjà ce nom")
    piece = DossierPiece(
        dossier_id=doss.id, libelle=libelle, obligatoire=body.obligatoire, statut="manquant", source="manuel",
    )
    session.add(piece)
    await session.commit()
    await session.refresh(piece)
    return DossierPieceOut(
        id=piece.id, libelle=piece.libelle, obligatoire=piece.obligatoire,
        statut=piece.statut, document_id=piece.document_id, source=piece.source,
    )


@router.delete("/{dossier_id}/pieces/{piece_id}", status_code=204)
async def delete_piece(
    dossier_id: UUID,
    piece_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Retire une rubrique — réservé aux pièces ajoutées à la main : une
    pièce standard ou issue du RC doit rester visible même vide, pour
    signaler le manque plutôt que le faire disparaître."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    piece = await session.get(DossierPiece, piece_id)
    if piece is None or piece.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Pièce introuvable")
    if piece.source != "manuel":
        raise HTTPException(status_code=400, detail="Seule une rubrique ajoutée manuellement peut être retirée")
    await session.delete(piece)
    await session.commit()


@router.get("/{dossier_id}/pieces/export")
async def export_pieces(
    dossier_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Compile toutes les pièces fournies (ou trouvées en patrimoine) en un
    seul PDF téléchargeable — le dossier administratif prêt à déposer,
    plutôt que de retélécharger chaque pièce une à une (§ export pièces)."""
    doss = await _get_owned_dossier(session, dossier_id, user)
    pdf_bytes, missing = await build_pieces_pdf(session, doss)
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in (doss.project_name or str(doss.id)))
    headers = {
        "Content-Disposition": f'attachment; filename="dossier_administratif_{safe_name}.pdf"',
        "X-Pieces-Manquantes": str(len(missing)),
    }
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


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


@router.post("/{dossier_id}/pieces/{piece_id}/upload", response_model=DossierPieceOut)
async def upload_piece(
    dossier_id: UUID,
    piece_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Dépose directement un fichier pour cette pièce — évite le détour
    « déposer en annexe, puis aller le choisir dans une liste déroulante ».
    Stocké en patrimoine (doc_type='administratif', jamais indexé pour le
    RAG — voir store_document) : réutilisable tel quel sur un futur dossier."""
    _require_write(user)
    doss = await _get_owned_dossier(session, dossier_id, user)
    piece = await session.get(DossierPiece, piece_id)
    if piece is None or piece.dossier_id != doss.id:
        raise HTTPException(status_code=404, detail="Pièce introuvable")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    doc, duplicate = await store_document(
        session, user, data, file.filename or "piece.bin",
        doc_role="patrimoine", doc_type="administratif", content_type=file.content_type,
    )
    if not duplicate:
        await session.flush()
    piece.document_id = doc.id
    piece.statut = "fourni"
    piece.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(piece)
    return DossierPieceOut(
        id=piece.id, libelle=piece.libelle, obligatoire=piece.obligatoire,
        statut=piece.statut, document_id=piece.document_id, source=piece.source,
    )


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

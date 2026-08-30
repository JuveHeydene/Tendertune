"""Alimentation de `outline_items`, `exigences` et `dossier_pieces` — §9,
Diagramme 5. Déterministe (LLM = étapes bornées, comme extract_graph),
PAS agentique — la couverture des exigences, elle, réutilise le CRAG
existant (app.rag.experts) sans rien réinventer.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.graph.entity_match import EntityMatchIndex
from app.models.pydantic import Complexite, Expert
from app.models.sql import ChunkRow, Document, DossierPiece, Dossier, ExigenceRow, OutlineItem
from app.rag.experts import run_expert
from app.services.db_client import session_factory
from app.services.ollama_llm import ollama_generate_json
from app.workflow.sections import DEFAULT_OUTLINE, archetype_for_key, archetype_for_title

log = logging.getLogger("btp.extract_structure")

# §5.3 — liste standard si le RC ne détaille pas explicitement les pièces
# attendues (cas fréquent).
STANDARD_PIECES: tuple[str, ...] = (
    "KBIS de moins de 3 mois",
    "Attestation d'assurance décennale en cours de validité",
    "Attestation de régularité fiscale",
    "Attestation de régularité sociale (URSSAF)",
    "DC1 — Lettre de candidature",
    "DC2 — Déclaration du candidat",
)

_OUTLINE_KEYWORDS = (
    "le mémoire technique comprendra",
    "le memoire technique comprendra",
    "structure de la réponse",
    "structure de la reponse",
    "composition du dossier",
    "composition du mémoire",
)

_PIECES_KEYWORDS = (
    "pièces à fournir",
    "pieces a fournir",
    "dossier administratif",
    "pièces de la candidature",
)

_OUTLINE_PROMPT = """Le texte suivant est un extrait de règlement de
consultation d'appel d'offres BTP. Il décrit la structure attendue du
mémoire technique. Extrais la liste ORDONNÉE des titres demandés.
Réponds UNIQUEMENT en JSON : {{"titres": ["...", "..."]}}
Texte :
{text}
"""

_EXIGENCES_PROMPT = """Tu extraies les exigences d'un extrait de dossier
d'appel d'offres BTP (DAO).
Catégories de type autorisées uniquement : eliminatoire, technique,
administrative, financiere, delai, reference.
Réponds UNIQUEMENT en JSON :
{{"exigences": [{{"libelle": "...", "type": "...", "obligatoire": true, "reference_dao": "..."}}]}}
Pas d'exigence si rien de clair. Texte :
{text}
"""

_PIECES_PROMPT = """Le texte suivant énumère les pièces administratives
demandées dans un appel d'offres BTP. Extrais la liste des pièces.
Réponds UNIQUEMENT en JSON : {{"pieces": ["...", "..."]}}
Texte :
{text}
"""


async def _rc_parents(session, document_id: UUID) -> list[ChunkRow]:
    rows = (
        await session.execute(
            select(ChunkRow).where(
                ChunkRow.document_id == document_id,
                ChunkRow.parent_id.is_(None),
                ChunkRow.section_type == "rc",
            )
        )
    ).scalars().all()
    return list(rows)


async def _all_parents(session, document_id: UUID) -> list[ChunkRow]:
    rows = (
        await session.execute(
            select(ChunkRow).where(
                ChunkRow.document_id == document_id,
                ChunkRow.parent_id.is_(None),
            )
        )
    ).scalars().all()
    return list(rows)


async def extract_outline(session, dossier: Dossier) -> int:
    """Retourne le nombre de sections insérées."""
    titres: list[str] | None = None
    if dossier.dao_document_id:
        rc_parents = await _rc_parents(session, dossier.dao_document_id)
        combined = "\n".join(p.text for p in rc_parents)
        lowered = combined.lower()
        if any(k in lowered for k in _OUTLINE_KEYWORDS):
            try:
                body = ollama_generate_json(_OUTLINE_PROMPT.format(text=combined[:4000]), timeout=90)
                candidates = [str(t).strip() for t in (body.get("titres") or []) if str(t).strip()]
                if candidates:
                    titres = candidates
            except Exception as exc:
                log.warning("extract_outline — LLM échoué, fallback DEFAULT_OUTLINE : %s", exc)

    n = 0
    if titres:
        for i, titre in enumerate(titres):
            key = f"section_{i}_{titre[:30].lower().replace(' ', '_')}"
            existing = (
                await session.execute(
                    select(OutlineItem).where(OutlineItem.dossier_id == dossier.id, OutlineItem.key == key)
                )
            ).scalar_one_or_none()
            if existing:
                continue
            session.add(
                OutlineItem(
                    dossier_id=dossier.id,
                    key=key,
                    heading_level=1,
                    title=titre,
                    sort_order=i,
                    status="todo",
                    archetype=archetype_for_title(titre),
                )
            )
            n += 1
    else:
        for i, (key, level, title) in enumerate(DEFAULT_OUTLINE):
            existing = (
                await session.execute(
                    select(OutlineItem).where(OutlineItem.dossier_id == dossier.id, OutlineItem.key == key)
                )
            ).scalar_one_or_none()
            if existing:
                continue
            session.add(
                OutlineItem(
                    dossier_id=dossier.id, key=key, heading_level=level, title=title,
                    sort_order=i, status="todo", archetype=archetype_for_key(key),
                )
            )
            n += 1
    await session.flush()
    log.info("extract_outline — %d sections insérées (dossier=%s, source=%s)", n, dossier.id, "RC" if titres else "défaut")
    return n


def _dedup_exigences(raw: list[dict]) -> list[dict]:
    """Réutilise la cascade fuzzy (Levenshtein/Jaccard/embedding) déjà
    construite pour les entités de graphe — un RC et un CCAP répètent
    souvent la même exigence sous une formulation légèrement différente."""
    index = EntityMatchIndex(use_embeddings=False)  # embeddings coûteux ici, fuzzy texte suffit
    kept: list[dict] = []
    for ex in raw:
        libelle = str(ex.get("libelle", "")).strip()
        if not libelle:
            continue
        hit = index.resolve(libelle)
        if hit is not None:
            continue  # déjà vu sous une formulation proche
        key = f"exigence:{len(kept)}"
        index.add(libelle, key)
        kept.append(ex)
    return kept


async def extract_exigences(session, dossier: Dossier) -> int:
    if not dossier.dao_document_id:
        return 0
    parents = await _all_parents(session, dossier.dao_document_id)
    log.info("extract_exigences — %d parents à traiter (pas de limite à 12), dossier=%s", len(parents), dossier.id)

    raw: list[dict] = []
    for parent in parents:
        try:
            body = ollama_generate_json(_EXIGENCES_PROMPT.format(text=parent.text[:3500]), timeout=90)
        except Exception as exc:
            log.warning("extract_exigences — échec LLM sur un parent : %s", exc)
            continue
        for ex in body.get("exigences") or []:
            etype = str(ex.get("type", "")).lower()
            if etype not in ("eliminatoire", "technique", "administrative", "financiere", "delai", "reference"):
                continue
            ex["_page_source"] = parent.page
            raw.append(ex)

    deduped = _dedup_exigences(raw)
    n = 0
    for ex in deduped:
        session.add(
            ExigenceRow(
                dossier_id=dossier.id,
                libelle=str(ex.get("libelle", "")).strip(),
                type=str(ex.get("type")).lower(),
                obligatoire=bool(ex.get("obligatoire", True)),
                page_source=ex.get("_page_source"),
                reference_dao=str(ex.get("reference_dao") or "") or None,
                statut="a_couvrir",
            )
        )
        n += 1
    await session.flush()
    log.info("extract_exigences — %d exigences insérées (dédup de %d brutes), dossier=%s", n, len(raw), dossier.id)
    return n


async def extract_checklist_administrative(session, dossier: Dossier) -> int:
    pieces: list[str] = list(STANDARD_PIECES)
    from_rc = False
    if dossier.dao_document_id:
        rc_parents = await _rc_parents(session, dossier.dao_document_id)
        combined = "\n".join(p.text for p in rc_parents)
        if any(k in combined.lower() for k in _PIECES_KEYWORDS):
            try:
                body = ollama_generate_json(_PIECES_PROMPT.format(text=combined[:4000]), timeout=90)
                candidates = [str(p).strip() for p in (body.get("pieces") or []) if str(p).strip()]
                if candidates:
                    pieces = candidates
                    from_rc = True
            except Exception as exc:
                log.warning("extract_checklist_administrative — LLM échoué, liste standard conservée : %s", exc)

    n = 0
    for libelle in pieces:
        existing = (
            await session.execute(
                select(DossierPiece).where(
                    DossierPiece.dossier_id == dossier.id, DossierPiece.libelle == libelle
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        # §5.3 — cherche un document déjà en patrimoine pour cette pièce
        # (le plus récent). Recherche par correspondance approximative sur
        # doc_type='administratif' — pas de lien fort possible sans une
        # taxonomie plus fine des pièces, assumé pour cette V2.
        candidate_doc = (
            await session.execute(
                select(Document)
                .where(Document.tenant_id == dossier.tenant_id, Document.doc_type == "administratif")
                .order_by(Document.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        session.add(
            DossierPiece(
                dossier_id=dossier.id,
                libelle=libelle,
                obligatoire=True,
                document_id=candidate_doc.id if candidate_doc else None,
                statut="trouve_patrimoine" if candidate_doc else "manquant",
                source="rc" if from_rc else "standard",
            )
        )
        n += 1
    await session.flush()
    log.info("extract_checklist_administrative — %d pièces insérées, dossier=%s", n, dossier.id)
    return n


async def extract_dossier_structure(ctx: dict, dossier_id: str) -> str:
    """Job ARQ — orchestre les 3 extractions déterministes (§9, §5.3)."""
    log.info("======== EXTRACT STRUCTURE DÉBUT dossier_id=%s ========", dossier_id)
    factory = session_factory()
    async with factory() as session:
        dossier = await session.get(Dossier, UUID(dossier_id))
        if dossier is None:
            log.error("EXTRACT STRUCTURE — dossier introuvable id=%s", dossier_id)
            return f"missing:{dossier_id}"
        dossier.status = "analyzing"
        dossier.updated_at = datetime.now(UTC)
        await session.commit()

        try:
            n_outline = await extract_outline(session, dossier)
            n_exigences = await extract_exigences(session, dossier)
            n_pieces = await extract_checklist_administrative(session, dossier)
            dossier.status = "generating"
            dossier.updated_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.exception("EXTRACT STRUCTURE ÉCHEC dossier_id=%s : %s", dossier_id, exc)
            return f"failed:{dossier_id}"

    log.info(
        "======== EXTRACT STRUCTURE FIN dossier_id=%s outline=%d exigences=%d pieces=%d ========",
        dossier_id, n_outline, n_exigences, n_pieces,
    )
    return f"done:{dossier_id}"


async def cover_exigence(exigence_id: UUID, *, tenant_id: UUID) -> None:
    """Réutilise le CRAG existant (app.rag.experts) — AUCUNE nouvelle
    mécanique de recherche, juste un nouvel appelant (§9 étape 4)."""
    factory = session_factory()
    async with factory() as session:
        exigence = await session.get(ExigenceRow, exigence_id)
        if exigence is None:
            return
        exigence.statut = "en_cours"
        await session.commit()

    resultat = await run_expert(
        Expert.patrimoine,
        exigence.libelle,
        tenant_id=tenant_id,
        dossier_id=exigence.dossier_id,
        message_id=None,
        sous_question_index=0,
        complexite=Complexite.complexe,
    )

    async with factory() as session:
        exigence = await session.get(ExigenceRow, exigence_id)
        if exigence is None:
            return
        if resultat.chunks:
            exigence.statut = "couverte"
            exigence.preuves_chunks = [c.chunk_id for c in resultat.chunks[:5]]
            exigence.couverte_at = datetime.now(UTC)
        else:
            exigence.statut = "non_couverte"
        exigence.updated_at = datetime.now(UTC)
        await session.commit()

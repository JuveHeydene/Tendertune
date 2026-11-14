"""Alimentation de `outline_items`, `exigences` et `dossier_pieces` — §9,
Diagramme 5. Déterministe (LLM = étapes bornées, comme extract_graph),
PAS agentique — la couverture des exigences, elle, réutilise le CRAG
existant (app.rag.experts) sans rien réinventer.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.graph.entity_match import EntityMatchIndex
from app.models.pydantic import Complexite, Expert, SourceContexte
from app.models.sql import (
    ChunkRow,
    Document,
    Dossier,
    DossierPiece,
    ExigenceRow,
    ExigenceSection,
    OutlineItem,
)
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

_EXIGENCES_PROMPT = """Tu extraies les exigences d'extraits d'un dossier
d'appel d'offres BTP (DAO). Le texte ci-dessous peut contenir PLUSIEURS
extraits séparés par "--- Extrait page N ---" : traite-les tous et cumule
toutes les exigences trouvées dans une seule liste.
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

_CLASSIFY_SECTIONS_PROMPT = """Tu associes des exigences d'un dossier
d'appel d'offres BTP aux sections du mémoire technique qui doivent y
répondre explicitement. Une exigence peut concerner PLUSIEURS sections, ou
aucune si elle ne correspond à rien de rédactionnel (ex. une pièce
administrative pure comme un KBIS n'a souvent aucune section dédiée) — dans
ce cas omets-la simplement, ne force pas une association.

Sections disponibles (index. titre [archétype]) :
{sections}

Exigences à classer (index. libellé [type]) :
{exigences}

Réponds UNIQUEMENT en JSON :
{{"associations": [{{"exigence_index": 1, "section_indices": [2, 5]}}]}}
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
                body = await asyncio.to_thread(
                    ollama_generate_json, _OUTLINE_PROMPT.format(text=combined[:4000]), timeout=90, num_ctx=2048
                )
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


_EXIGENCES_BATCH_MAX_CHARS = 14000  # ~3500 tokens, avec num_ctx=4096 explicite (marge prompt+JSON)
_EXIGENCES_PARENT_MAX_CHARS = 3500
_EXIGENCES_NUM_CTX = 4096


def _batch_parents(parents: list[ChunkRow], max_chars: int = _EXIGENCES_BATCH_MAX_CHARS) -> list[list[ChunkRow]]:
    """Regroupe des chunks parents consécutifs jusqu'à `max_chars` cumulés —
    un DAO volumineux (150+ pages) fait sinon 1 appel LLM séquentiel par
    parent (des heures, et le job dépasse le job_timeout ARQ, qui le relance
    depuis zéro en boucle sans jamais aboutir). Contrepartie acceptée : la
    page source d'une exigence devient l'ancre du batch, pas une page
    précise (choix explicite, moins fin mais ~5-8x plus rapide)."""
    batches: list[list[ChunkRow]] = []
    current: list[ChunkRow] = []
    current_len = 0
    for p in parents:
        text_len = min(len(p.text), _EXIGENCES_PARENT_MAX_CHARS)
        if current and current_len + text_len > max_chars:
            batches.append(current)
            current = []
            current_len = 0
        current.append(p)
        current_len += text_len
    if current:
        batches.append(current)
    return batches


async def extract_exigences(session, dossier: Dossier) -> int:
    if not dossier.dao_document_id:
        return 0
    # BPU (bordereau de prix unitaires) = tableaux de prix, jamais des
    # exigences qualitatives — l'exclure évite des appels LLM inutiles sur
    # un très gros DAO.
    parents = [p for p in await _all_parents(session, dossier.dao_document_id) if p.section_type != "bpu"]
    batches = _batch_parents(parents)
    log.info(
        "extract_exigences — %d parents regroupés en %d appels LLM (dossier=%s)",
        len(parents), len(batches), dossier.id,
    )

    raw: list[dict] = []
    for batch in batches:
        combined = "\n\n".join(
            f"--- Extrait page {p.page if p.page is not None else '?'} ---\n{p.text[:_EXIGENCES_PARENT_MAX_CHARS]}"
            for p in batch
        )
        pages = [p.page for p in batch if p.page is not None]
        page_anchor = min(pages) if pages else None
        try:
            body = await asyncio.to_thread(
                ollama_generate_json,
                _EXIGENCES_PROMPT.format(text=combined[:15000]),
                timeout=150,
                num_ctx=_EXIGENCES_NUM_CTX,
            )
        except Exception as exc:
            log.warning("extract_exigences — échec LLM sur un batch (%d parents) : %s", len(batch), exc)
            continue
        for ex in body.get("exigences") or []:
            etype = str(ex.get("type", "")).lower()
            if etype not in ("eliminatoire", "technique", "administrative", "financiere", "delai", "reference"):
                continue
            ex["_page_source"] = page_anchor
            raw.append(ex)

    deduped = _dedup_exigences(raw)

    # Purge avant réinsertion — sans ça, relancer l'analyse d'un dossier
    # (reprise après échec partiel, ou nouvelle analyse volontaire) doublait
    # les exigences à chaque passage (même bug que les vecteurs Qdrant
    # orphelins côté ingestion, §app/ingest/index_qdrant.delete_by_document).
    existing = (
        await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == dossier.id))
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()

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
                body = await asyncio.to_thread(
                    ollama_generate_json, _PIECES_PROMPT.format(text=combined[:4000]), timeout=90, num_ctx=2048
                )
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

        # Ré-analyse = remplacement, jamais un cumul. Sans ça, deux exécutions
        # sur le même dossier (retry ARQ après un job_timeout, double-clic,
        # nouveau DAO chargé...) dupliquent les exigences — observé en
        # conditions réelles : un job relancé après coup a bien failli
        # doubler les 95 exigences déjà extraites avec succès.
        await session.execute(delete(ExigenceRow).where(ExigenceRow.dossier_id == dossier.id))
        await session.execute(delete(OutlineItem).where(OutlineItem.dossier_id == dossier.id))
        await session.flush()

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


_CLASSIFY_BATCH_SIZE = 25  # ~25 libellés courts + la liste des sections tient large dans num_ctx=4096


async def classify_exigences_sections(session, dossier: Dossier) -> int:
    """Associe chaque exigence aux sections du plan qui doivent y répondre
    (§ liaison exigences/sections). Ne touche JAMAIS un couple déjà décidé
    (confirmé ou exclu) — seuls les couples (exigence, section) inédits
    reçoivent une proposition LLM, via ON CONFLICT DO NOTHING sur la
    contrainte unique (exigence_id, outline_item_id) : relancer la
    classification après qu'un humain a confirmé/exclu des liens ne les
    écrase jamais, ça ne fait que compléter les couples encore inconnus."""
    outline_rows = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == dossier.id).order_by(OutlineItem.sort_order)
        )
    ).scalars().all()
    exigence_rows = (
        await session.execute(select(ExigenceRow).where(ExigenceRow.dossier_id == dossier.id))
    ).scalars().all()
    if not outline_rows or not exigence_rows:
        return 0

    sections_block = "\n".join(f"{i + 1}. {o.title} [{o.archetype}]" for i, o in enumerate(outline_rows))

    n_created = 0
    for start in range(0, len(exigence_rows), _CLASSIFY_BATCH_SIZE):
        batch = exigence_rows[start : start + _CLASSIFY_BATCH_SIZE]
        exigences_block = "\n".join(f"{i + 1}. {e.libelle} [{e.type}]" for i, e in enumerate(batch))
        try:
            body = await asyncio.to_thread(
                ollama_generate_json,
                _CLASSIFY_SECTIONS_PROMPT.format(sections=sections_block, exigences=exigences_block),
                timeout=150,
                num_ctx=4096,
            )
        except Exception as exc:
            log.warning("classify_exigences_sections — échec LLM sur un batch (%d exigences) : %s", len(batch), exc)
            continue

        rows_to_insert: list[dict] = []
        for assoc in body.get("associations") or []:
            try:
                ex_idx = int(assoc.get("exigence_index")) - 1
            except (TypeError, ValueError):
                continue
            if not (0 <= ex_idx < len(batch)):
                continue
            for sec_idx_raw in assoc.get("section_indices") or []:
                try:
                    sec_idx = int(sec_idx_raw) - 1
                except (TypeError, ValueError):
                    continue
                if not (0 <= sec_idx < len(outline_rows)):
                    continue
                rows_to_insert.append(
                    {
                        "exigence_id": batch[ex_idx].id,
                        "outline_item_id": outline_rows[sec_idx].id,
                        "origine": "llm",
                        "statut": "proposee",
                    }
                )
        if not rows_to_insert:
            continue
        stmt = pg_insert(ExigenceSection).values(rows_to_insert).on_conflict_do_nothing(
            index_elements=["exigence_id", "outline_item_id"]
        )
        result = await session.execute(stmt)
        n_created += result.rowcount or 0

    await session.flush()
    log.info(
        "classify_exigences_sections — %d liens créés (dossier=%s, %d exigences, %d sections)",
        n_created, dossier.id, len(exigence_rows), len(outline_rows),
    )
    return n_created


async def classify_dossier_sections(ctx: dict, dossier_id: str) -> str:
    """Job ARQ — classification exigences/sections. Séparé de
    extract_dossier_structure : peut être relancé indépendamment (ex. après
    ajout manuel d'exigences ou de sections) sans retoucher outline/
    exigences déjà extraits."""
    log.info("======== CLASSIFY SECTIONS DÉBUT dossier_id=%s ========", dossier_id)
    factory = session_factory()
    async with factory() as session:
        dossier = await session.get(Dossier, UUID(dossier_id))
        if dossier is None:
            log.error("CLASSIFY SECTIONS — dossier introuvable id=%s", dossier_id)
            return f"missing:{dossier_id}"
        dossier.classification_status = "running"
        dossier.classification_error = None
        dossier.updated_at = datetime.now(UTC)
        await session.commit()

        try:
            n = await classify_exigences_sections(session, dossier)
            dossier.classification_status = "ready"
            dossier.updated_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            dossier = await session.get(Dossier, UUID(dossier_id))
            if dossier is not None:
                dossier.classification_status = "failed"
                dossier.classification_error = f"{type(exc).__name__}: {exc}"[:2000]
                dossier.updated_at = datetime.now(UTC)
                await session.commit()
            log.exception("CLASSIFY SECTIONS ÉCHEC dossier_id=%s : %s", dossier_id, exc)
            return f"failed:{dossier_id}"

    log.info("======== CLASSIFY SECTIONS FIN dossier_id=%s liens=%d ========", dossier_id, n)
    return f"ready:{dossier_id}"


async def cover_exigence(exigence_id: UUID, *, tenant_id: UUID) -> None:
    """Réutilise le CRAG existant (app.rag.experts) — AUCUNE nouvelle
    mécanique de recherche, juste un nouvel appelant (§9 étape 4).

    Le passage à `statut="en_cours"` est fait par l'appelant (endpoint HTTP,
    voir app/api/dossiers.py) AVANT de planifier cette tâche de fond, pas
    ici — sinon la fenêtre entre le clic et la première ligne de cette
    fonction laissait passer un second clic (double recherche concurrente)."""
    factory = session_factory()
    async with factory() as session:
        exigence = await session.get(ExigenceRow, exigence_id)
        if exigence is None:
            return
        libelle = exigence.libelle
        dossier_id = exigence.dossier_id

    resultat = await run_expert(
        Expert.patrimoine,
        libelle,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        message_id=None,
        sous_question_index=0,
        complexite=Complexite.complexe,
    )

    async with factory() as session:
        exigence = await session.get(ExigenceRow, exigence_id)
        if exigence is None:
            return
        # `resultat.chunks` seul ne suffit PAS à conclure à une couverture :
        # en cas d'abstention CRAG (aucun contexte jugé "correct" après 3
        # tentatives), run_expert renvoie quand même les derniers candidats
        # trouvés, non jugés pertinents — les traiter comme "couverte" serait
        # trompeur. On distingue donc :
        #  - source=retrieval (grading a validé le contexte)      → couverte
        #  - abstention avec des candidats quand même remontés    → a_revoir
        #    (décision humaine nécessaire, ni couvert ni exclu)
        #  - abstention sans le moindre candidat                  → non_couverte
        if resultat.source == SourceContexte.retrieval and resultat.chunks:
            exigence.statut = "couverte"
            exigence.preuves_chunks = [c.chunk_id for c in resultat.chunks[:5]]
            exigence.couverte_at = datetime.now(UTC)
        elif resultat.chunks:
            exigence.statut = "a_revoir"
            exigence.preuves_chunks = [c.chunk_id for c in resultat.chunks[:5]]
            exigence.couverte_at = None
        else:
            exigence.statut = "non_couverte"
            exigence.preuves_chunks = []
            exigence.couverte_at = None
        exigence.updated_at = datetime.now(UTC)
        await session.commit()

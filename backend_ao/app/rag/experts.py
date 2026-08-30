"""Boucle CRAG bornée, par expert — §5.2/§5.3, Diagramme 3.

Chaque expert est un agent de RÉCUPÉRATION scopé (§1.1) : il ne rédige
jamais. Il retourne un `ResultatExpert` (contexte gradé ou abstention) que
l'agrégateur combine ensuite pour le générateur unique.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pydantic import Complexite, Expert, ExtraitCite, Grade, ResultatExpert, SourceContexte
from app.models.sql import RetrievalTrace
from app.rag.fusion import rrf_fuse
from app.rag.grading import grade_context
from app.rag.hybrid_retriever import retrieve_dense
from app.rag.rerank import rerank
from app.rag.sparse_retriever import retrieve_sparse
from app.services.db_client import session_factory
from app.services.ollama_llm import ollama_generate_json

log = logging.getLogger("btp.experts")

MAX_ITER = 3

# §1.1 / §3.1 — scope de chaque expert. `section_types=None` = pas de filtre
# de ce type (le financier et le graphe ont leur propre mécanisme, voir plus
# bas et graph_expert.py).
EXPERT_SCOPES: dict[Expert, dict] = {
    Expert.juridique: {"section_types": ["rc", "ccap"], "doc_roles": None},
    Expert.technique: {"section_types": ["cctp"], "doc_roles": None},
    # Simplification assumée : DPGF/BPU restent des chunks texte (pas de
    # table SQL structurée dans ce pipeline pour l'instant) — le scope
    # documentaire suffit à isoler les pièces financières du reste.
    Expert.financier: {"section_types": ["dpgf", "bpu"], "doc_roles": None},
    Expert.patrimoine: {"section_types": None, "doc_roles": ["patrimoine", "dao_archive"]},
}

_REWRITE_VARIANT_PROMPT = """Reformule cette requête de recherche documentaire
avec un angle différent (synonymes, reformulation), pour retrouver des
passages qu'une première recherche aurait pu manquer (RAG-08 §4, multi-query).
Réponds UNIQUEMENT en JSON : {{"query": "..."}}

Requête initiale : {query}
"""


async def _hybrid_pass(
    session: AsyncSession,
    query: str,
    *,
    tenant_id: UUID,
    scope: dict,
    dossier_id: UUID | None,
    top_k: int,
    drop_section_type: bool = False,
    drop_doc_role: bool = False,
) -> list[dict]:
    section_types = None if drop_section_type else scope.get("section_types")
    doc_roles = None if drop_doc_role else scope.get("doc_roles")

    dense_hits = await retrieve_dense(
        query,
        tenant_id=tenant_id,
        top_k=top_k,
        section_types=section_types,
        doc_roles=doc_roles,
        dossier_id=dossier_id,
    )
    sparse_hits = await retrieve_sparse(
        session,
        query,
        tenant_id=tenant_id,
        top_k=top_k,
        section_types=section_types,
        doc_roles=doc_roles,
        dossier_id=dossier_id,
    )
    fused = rrf_fuse(dense_hits, sparse_hits)
    return rerank(query, fused, top_n=8)


async def run_expert(
    expert: Expert,
    query: str,
    *,
    tenant_id: UUID,
    dossier_id: UUID | None,
    message_id: UUID | None,
    sous_question_index: int,
    complexite: Complexite,
) -> ResultatExpert:
    """Ouvre et gère sa PROPRE session (au lieu d'en recevoir une partagée) :
    plusieurs experts peuvent ainsi tourner en vrai parallèle via
    `asyncio.gather` (§1 étape 6, §5.5) sans se disputer une AsyncSession
    unique — SQLAlchemy AsyncSession n'est pas sûre pour un usage concurrent
    depuis plusieurs coroutines entrelacées sur le même objet."""
    factory = session_factory()
    async with factory() as session:
        result = await _run_expert_with_session(
            session,
            expert,
            query,
            tenant_id=tenant_id,
            dossier_id=dossier_id,
            message_id=message_id,
            sous_question_index=sous_question_index,
            complexite=complexite,
        )
        await session.commit()
        return result


async def _run_expert_with_session(
    session: AsyncSession,
    expert: Expert,
    query: str,
    *,
    tenant_id: UUID,
    dossier_id: UUID | None,
    message_id: UUID | None,
    sous_question_index: int,
    complexite: Complexite,
) -> ResultatExpert:
    scope = EXPERT_SCOPES.get(expert, {"section_types": None, "doc_roles": None})
    current_query = query

    if complexite == Complexite.simple:
        # §5.1 — Adaptive : PAS de grading, on fait confiance au Top-8.
        top8 = await _hybrid_pass(
            session, current_query, tenant_id=tenant_id, scope=scope, dossier_id=dossier_id, top_k=8
        )
        return ResultatExpert(
            expert=expert,
            source=SourceContexte.retrieval if top8 else SourceContexte.abstention,
            chunks=[_to_extrait(c) for c in top8],
            tentatives=1,
        )

    drop_section_type = False
    drop_doc_role = False
    last_chunks: list[dict] = []
    for tentative in range(1, MAX_ITER + 1):
        candidates = await _hybrid_pass(
            session,
            current_query,
            tenant_id=tenant_id,
            scope=scope,
            dossier_id=dossier_id,
            top_k=50,
            drop_section_type=drop_section_type,
            drop_doc_role=drop_doc_role,
        )
        last_chunks = candidates
        grade, grade_method = grade_context(current_query, candidates)

        session.add(
            RetrievalTrace(
                tenant_id=tenant_id,
                message_id=message_id,
                sous_question_index=sous_question_index,
                sous_question_texte=query,
                expert=expert.value,
                tentative=tentative,
                query_utilisee=current_query,
                filtres={
                    "section_types": None if drop_section_type else scope.get("section_types"),
                    "doc_roles": None if drop_doc_role else scope.get("doc_roles"),
                },
                grade=grade.value,
                grade_method=grade_method,
                chunks_retournes=[{"chunk_id": c.get("chunk_id"), "score": c.get("rerank_score")} for c in candidates[:8]],
                abstention=False,
            )
        )
        await session.flush()

        if grade == Grade.correct:
            return ResultatExpert(
                expert=expert,
                source=SourceContexte.retrieval,
                chunks=[_to_extrait(c) for c in candidates],
                tentatives=tentative,
            )
        if tentative == MAX_ITER:
            break
        if grade == Grade.ambigu:
            # ÉLARGIR, pas reformuler (§5.2)
            if not drop_section_type and scope.get("section_types"):
                drop_section_type = True
            elif not drop_doc_role and scope.get("doc_roles"):
                drop_doc_role = True
        else:  # Incorrect → reformuler
            current_query = await _reformulate(current_query)

    session.add(
        RetrievalTrace(
            tenant_id=tenant_id,
            message_id=message_id,
            sous_question_index=sous_question_index,
            sous_question_texte=query,
            expert=expert.value,
            tentative=MAX_ITER,
            query_utilisee=current_query,
            filtres={},
            grade=None,
            grade_method=None,
            chunks_retournes=[],
            abstention=True,
        )
    )
    await session.flush()
    log.info("Expert %s — abstention après %d tentatives (query=%r)", expert.value, MAX_ITER, query)
    return ResultatExpert(
        expert=expert,
        source=SourceContexte.abstention,
        chunks=[_to_extrait(c) for c in last_chunks],
        tentatives=MAX_ITER,
        raison_abstention=f"Aucun résultat jugé suffisant après {MAX_ITER} tentatives.",
    )


async def _reformulate(query: str) -> str:
    try:
        body = ollama_generate_json(_REWRITE_VARIANT_PROMPT.format(query=query), timeout=45)
        variant = str(body.get("query") or "").strip()
        return variant or query
    except Exception as exc:
        log.warning("_reformulate — échec, requête inchangée : %s", exc)
        return query


def _to_extrait(hit: dict) -> ExtraitCite:
    return ExtraitCite(
        chunk_id=str(hit.get("chunk_id") or ""),
        score=float(hit.get("rerank_score", hit.get("score", 0.0)) or 0.0),
        page=hit.get("page"),
        texte=hit.get("text") or "",
        heading_path=hit.get("heading_path"),
    )

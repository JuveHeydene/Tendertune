"""Orchestrateur V2 — Diagramme 2. Rewrite → Superviseur → dispatch experts
(en parallèle) → agrégation. Ne génère rien : c'est le nœud generate (§10)
qui a la main ensuite, une seule fois, sur le contexte déjà agrégé ici.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.models.pydantic import Complexite, Expert, Intent, ResultatExpert, SousQuestion, SuperviseurOutput
from app.rag.experts import run_expert
from app.rag.graph_expert import run_graph_expert
from app.workflow.nodes.aggregate import AggregatedContext, aggregate
from app.workflow.nodes.rewrite import rewrite_query
from app.workflow.nodes.superviseur import run_superviseur

log = logging.getLogger("btp.agentic")


async def _dispatch_sous_question(
    sous_question: SousQuestion,
    *,
    tenant_id: UUID,
    dossier_id: UUID | None,
    message_id: UUID | None,
    index: int,
) -> list[ResultatExpert] | None:
    if not sous_question.experts:
        # Règle R9 (§8.2) — absence VOLONTAIRE de recherche, jamais une
        # abstention. Rien à dispatcher.
        return None

    tasks = []
    for expert in sous_question.experts:
        if expert == Expert.graphe:
            tasks.append(run_graph_expert(sous_question.texte, tenant_id=tenant_id))
        else:
            tasks.append(
                run_expert(
                    expert,
                    sous_question.texte,
                    tenant_id=tenant_id,
                    dossier_id=dossier_id,
                    message_id=message_id,
                    sous_question_index=index,
                    complexite=sous_question.complexite,
                )
            )
    return list(await asyncio.gather(*tasks))


async def run_agentic_retrieval(
    raw_query: str,
    history: list[dict] | None,
    *,
    tenant_id: UUID,
    dossier_id: UUID | None,
    message_id: UUID | None,
) -> tuple[str, SuperviseurOutput, AggregatedContext | None]:
    """Retourne (query_clean, sortie_superviseur, contexte_agrégé_ou_None).

    contexte_agrégé est None pour smalltalk/export/clarification_needed —
    ces intentions ne passent jamais par le retrieval (déterministe, §1)."""

    query_clean = await asyncio.to_thread(rewrite_query, raw_query, history)
    superviseur_output = await asyncio.to_thread(run_superviseur, query_clean, history)

    if superviseur_output.intent not in (Intent.hybrid_rag, Intent.run_section):
        return query_clean, superviseur_output, None

    # §1 étape 6 / §5.5 — sous-questions dispatchées EN PARALLÈLE : le cas
    # dominant dans ce domaine est indépendant (cf. §5.5, limite assumée sur
    # le multi-hop séquentiel, hors périmètre V2).
    dispatch_tasks = [
        _dispatch_sous_question(
            sq, tenant_id=tenant_id, dossier_id=dossier_id, message_id=message_id, index=i
        )
        for i, sq in enumerate(superviseur_output.sous_questions)
    ]
    resultats_par_sous_question = await asyncio.gather(*dispatch_tasks)

    aggregated = aggregate(list(zip(superviseur_output.sous_questions, resultats_par_sous_question, strict=True)))
    log.info(
        "agentic_pipeline — intent=%s sous_questions=%d citations=%d abstentions=%d",
        superviseur_output.intent.value,
        len(superviseur_output.sous_questions),
        len(aggregated.citations),
        len(aggregated.abstentions),
    )
    return query_clean, superviseur_output, aggregated

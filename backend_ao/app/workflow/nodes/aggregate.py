"""Agrégateur — §1 étape 7, §5.4. Fusionne les résultats de TOUTES les
sous-questions et de TOUS les experts sollicités en un contexte numéroté
unique, avant le générateur unique (§1.1 : les experts ne rédigent jamais).

Distingue explicitement 3 sources par sous-question (§5.4) :
  retrieval    → au moins un expert a cherché et trouvé (Correct)
  abstention   → un expert a cherché et épuisé ses tentatives sans succès
  conversation → experts=[] (règle R9) : aucune recherche n'a été tentée

Seule "abstention" doit déclencher une alerte côté UI — jamais "conversation".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.pydantic import ResultatExpert, SourceContexte, SousQuestion


@dataclass
class AggregatedContext:
    context_text: str
    citations: list[str] = field(default_factory=list)
    abstentions: list[str] = field(default_factory=list)
    relations_graphe: list[dict] = field(default_factory=list)
    experts_par_citation: dict[str, str] = field(default_factory=dict)  # chunk_id -> expert


def aggregate(
    sous_questions_resultats: list[tuple[SousQuestion, list[ResultatExpert] | None]],
) -> AggregatedContext:
    parts: list[str] = []
    citations: list[str] = []
    abstentions: list[str] = []
    relations: list[dict] = []
    experts_par_citation: dict[str, str] = {}

    numero = 1
    for sous_question, resultats in sous_questions_resultats:
        if resultats is None:
            # experts=[] (règle R9) — rien à agréger, le générateur s'appuiera
            # sur l'historique de conversation. PAS une abstention.
            continue
        for resultat in resultats:
            if resultat.source == SourceContexte.abstention:
                raison = resultat.raison_abstention or "aucune information pertinente trouvée"
                abstentions.append(
                    f"« {sous_question.texte} » (expert {resultat.expert.value}) : {raison}"
                )
                continue
            if resultat.source != SourceContexte.retrieval:
                continue
            for chunk in resultat.chunks:
                heading = chunk.heading_path or ""
                page = chunk.page if chunk.page is not None else "?"
                parts.append(f"[{numero}] p.{page} {heading} (expert: {resultat.expert.value})\n{chunk.texte[:12000]}")
                citations.append(chunk.chunk_id)
                experts_par_citation[chunk.chunk_id] = resultat.expert.value
                numero += 1
            relations.extend(resultat.relations_graphe)

    context_text = "\n\n".join(parts) if parts else (
        "(aucun extrait de recherche documentaire pour cette demande — "
        "s'appuyer sur l'historique de conversation le cas échéant.)"
    )
    return AggregatedContext(
        context_text=context_text,
        citations=citations,
        abstentions=abstentions,
        relations_graphe=relations,
        experts_par_citation=experts_par_citation,
    )

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

import logging
from dataclasses import dataclass, field

from app.models.pydantic import ResultatExpert, SourceContexte, SousQuestion

log = logging.getLogger("btp.aggregate")

# Budget de caractères pour le contexte agrégé TOTAL — avant cette limite,
# seul chaque CHUNK était plafonné (12000 caractères), sans borne sur le
# nombre de chunks cumulés (jusqu'à 50 par sous-question, 4 sous-questions
# max) ni sur la taille totale. Résultat réel observé : un contexte assez
# gros pour dépasser même un num_ctx généreux côté Ollama une fois ajoutées
# les instructions, les exigences liées et le texte existant (mode "ajoute")
# — le prompt entier se faisait tronquer en silence par Ollama, coupant
# souvent le schéma JSON attendu en fin de prompt (§ génération non aboutie).
# ~4 caractères/token en français : 20000 caractères ≈ 5000 tokens, laisse
# de la marge dans un num_ctx=8192 pour le reste du prompt ET la réponse.
MAX_CONTEXT_CHARS = 20000


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
    total_chars = 0
    truncated = False
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
                if total_chars >= MAX_CONTEXT_CHARS:
                    # Ne PAS ajouter ce chunk à citations/experts_par_citation
                    # non plus — sinon _validate() (generate_section.py)
                    # accepterait comme "connu" un id que le LLM n'a en
                    # réalité jamais vu dans son contexte.
                    truncated = True
                    continue
                heading = chunk.heading_path or ""
                page = chunk.page if chunk.page is not None else "?"
                piece = f"[{numero}] p.{page} {heading} (expert: {resultat.expert.value})\n{chunk.texte[:12000]}"
                parts.append(piece)
                total_chars += len(piece)
                citations.append(chunk.chunk_id)
                experts_par_citation[chunk.chunk_id] = resultat.expert.value
                numero += 1
            relations.extend(resultat.relations_graphe)

    if truncated:
        log.warning(
            "aggregate — contexte plafonné à %d caractères (%d extraits retenus) — "
            "des extraits moins prioritaires ont été omis pour ne pas dépasser "
            "la fenêtre de contexte du modèle",
            MAX_CONTEXT_CHARS, len(parts),
        )

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

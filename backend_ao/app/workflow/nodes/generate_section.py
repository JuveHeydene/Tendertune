"""Génération d'une section — §10 (archétypes) + §1 étape 8/9 (validation).

Un seul générateur, un seul appel par tentative (§1.1 : les experts ne
rédigent jamais). Le choix du prompt selon `outline_items.archetype` est un
LOOKUP déterministe (le code décide), pas une décision d'agent — voir §10
pour le raisonnement complet.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from pydantic import ValidationError

from app.models.pydantic import Bloc, SectionGeneree
from app.services.chat_history import format_history
from app.services.ollama_llm import ollama_generate_json
from app.workflow.nodes.aggregate import AggregatedContext

log = logging.getLogger("btp.generate_section")

MAX_ESSAIS = 2

_ARCHETYPE_GUIDANCE: dict[str, str] = {
    "institutionnelle": (
        "Ton commercial et professionnel. Mets en avant les chiffres clés de "
        "l'entreprise (effectifs, ancienneté, chiffre d'affaires si disponible). "
        "Les citations ne sont pas obligatoires pour cette section."
    ),
    "factuelle": (
        "Privilégie les listes et les quantités précises (moyens, équipements, "
        "références, délais). CHAQUE fait chiffré DOIT porter une citation [n] "
        "présente dans le contexte fourni."
    ),
    "narrative": (
        "Rédige une prose structurée en phases ou étapes claires (compréhension "
        "de la mission, méthodologie, organisation). Un sous-titre (H3 maximum) "
        "peut structurer les grandes phases."
    ),
    "conformite": (
        "Décris la politique et les normes appliquées (qualité, sécurité, "
        "environnement). Chaque certification citée doit porter une référence [n]."
    ),
}
_DEFAULT_GUIDANCE = _ARCHETYPE_GUIDANCE["factuelle"]

_PROMPT = """Tu es rédacteur d'un mémoire technique d'appel d'offres BTP (français).

Section à rédiger : « {titre} » (clé : {section_key}).
Le TITRE est FIXE, tu ne l'écris PAS toi-même dans les blocs (pas de H1/H2).
Consigne spécifique à ce type de section : {guidance}

Règles STRICTES :
- Utilise UNIQUEMENT les extraits numérotés du contexte pour les faits.
- Si une information manque, ajoute-la dans "abstentions", n'invente RIEN.
- Un bloc type="sous_titre" ne dépasse jamais heading_level=3.
- Un bloc type="image" doit avoir document_id renseigné avec un id du
  contexte (jamais un id inventé).
{consigne_extra}

Réponds UNIQUEMENT en JSON, selon ce schéma :
{{
  "section_key": "{section_key}",
  "titre": "{titre}",
  "blocs": [{{"type": "paragraphe|liste|tableau_md|sous_titre|image", "heading_level": null, "document_id": null, "texte": "..."}}],
  "citations": ["chunk_id", "..."],
  "exigences_couvertes": [],
  "abstentions": ["..."]
}}

{history}

Contexte (extraits numérotés, avec l'expert qui les a trouvés) :
{context}

Abstentions déjà connues (aucune recherche ne les a couvertes, à mentionner) :
{abstentions}
"""


def _validate(section: SectionGeneree, aggregated: AggregatedContext) -> list[str]:
    """Validateur déterministe (§1 étape 9) : erreurs trouvées, liste vide = OK."""
    errors: list[str] = []
    valid_chunk_ids = set(aggregated.citations)
    for c in section.citations:
        if c not in valid_chunk_ids:
            errors.append(f"citation inexistante : {c}")
    for bloc in section.blocs:
        if bloc.type == "sous_titre" and (bloc.heading_level or 0) > 3:
            errors.append(f"heading_level > 3 sur un sous_titre : {bloc.heading_level}")
        if bloc.texte.strip().startswith("# "):
            errors.append("un bloc contient un H1 littéral — interdit")
        if bloc.type == "image":
            if not bloc.document_id:
                errors.append("bloc image sans document_id")
            elif bloc.document_id not in valid_chunk_ids and bloc.document_id not in aggregated.experts_par_citation:
                # Vérification best-effort : un id d'image doit au moins être
                # un identifiant connu du contexte agrégé.
                errors.append(f"bloc image avec document_id inconnu du contexte : {bloc.document_id}")
    return errors


async def generate_section(
    *,
    section_key: str,
    titre: str,
    archetype: str,
    aggregated: AggregatedContext,
    history: list[dict] | None,
    custom_instruction: str | None = None,
) -> SectionGeneree:
    """Génère (et valide, avec retry borné) une section — jamais plus de
    MAX_ESSAIS appels LLM (garde-fou, même famille que max_iter CRAG)."""

    guidance = _ARCHETYPE_GUIDANCE.get(archetype, _DEFAULT_GUIDANCE)
    consigne_extra = f"Consigne complémentaire de l'utilisateur : {custom_instruction}" if custom_instruction else ""
    prompt = _PROMPT.format(
        titre=titre,
        section_key=section_key,
        guidance=guidance,
        consigne_extra=consigne_extra,
        history=format_history(history) or "",
        context=aggregated.context_text,
        abstentions="\n".join(f"- {a}" for a in aggregated.abstentions) or "(aucune)",
    )

    last_error: Exception | None = None
    for essai in range(1, MAX_ESSAIS + 1):
        try:
            body = await asyncio.to_thread(partial(ollama_generate_json, prompt, timeout=180))
        except Exception as exc:
            last_error = exc
            log.warning("generate_section — appel LLM échoué (essai %d) : %s", essai, exc)
            continue

        try:
            section = SectionGeneree.model_validate(body)
        except ValidationError as exc:
            last_error = exc
            log.warning("generate_section — JSON invalide (essai %d) : %s", essai, exc)
            prompt += f"\n\nERREUR précédente à corriger : {exc}\nRéponds à nouveau en JSON valide."
            continue

        errors = _validate(section, aggregated)
        if not errors:
            return section
        log.warning("generate_section — validation échouée (essai %d) : %s", essai, errors)
        prompt += "\n\nERREURS à corriger : " + "; ".join(errors)

    log.error("generate_section — abandon après %d essais, section minimale renvoyée", MAX_ESSAIS)
    return SectionGeneree(
        section_key=section_key,
        titre=titre,
        blocs=[Bloc(type="paragraphe", texte="[Génération non aboutie — voir logs]")],
        abstentions=aggregated.abstentions + (["Échec technique de génération."] if last_error else []),
    )


def section_to_markdown(section: SectionGeneree) -> str:
    """Rendu markdown d'une SectionGeneree — pour l'affichage chat/preview et
    les exports texte/markdown. Un bloc image est représenté par une
    référence explicite : l'insertion réelle dans le DOCX suppose une
    confirmation humaine (§5.4) faite depuis l'écran de revue, pas ici."""

    lines: list[str] = []
    for bloc in section.blocs:
        if bloc.type == "sous_titre":
            level = min(max(bloc.heading_level or 3, 1), 3)
            lines.append(f"{'#' * (level + 1)} {bloc.texte}")
        elif bloc.type == "liste":
            for item in bloc.texte.split("\n"):
                item = item.strip()
                if item:
                    lines.append(f"- {item.lstrip('-').strip()}")
        elif bloc.type == "image":
            lines.append(f"[Image proposée : {bloc.document_id} — à confirmer en revue]")
        else:
            lines.append(bloc.texte)
        lines.append("")
    if section.abstentions:
        lines.append("**Points non couverts :**")
        for a in section.abstentions:
            lines.append(f"- ⚠️ {a}")
    return "\n".join(lines).strip()

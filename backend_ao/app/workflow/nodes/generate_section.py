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
{grounding_rule}
- Le contexte patrimoine fourni est un EXEMPLE de travaux/méthodes déjà
  réalisés par l'entreprise, PAS un texte à recopier : ce projet est
  NOUVEAU, rédige un texte adapté à SES spécificités qui s'inspire du
  patrimoine sans le paraphraser mot pour mot.
- Un bloc type="sous_titre" ne dépasse jamais heading_level=3.
- Un bloc type="image" a pour document_id le NUMÉRO entre crochets de
  l'extrait du contexte (ex: 3) — jamais un autre identifiant, tu ne connais
  pas l'identifiant réel de l'extrait, seulement son numéro.
- Dans "citations" et pour "document_id" d'une image : utilise UNIQUEMENT le
  NUMÉRO entre crochets affiché devant chaque extrait du contexte (1, 2,
  3...), jamais un autre texte — tu n'as accès à aucun autre identifiant.
{consigne_extra}
{exigences_section}
{existing_content_section}
Réponds UNIQUEMENT en JSON, selon ce schéma :
{{
  "section_key": "{section_key}",
  "titre": "{titre}",
  "blocs": [{{"type": "paragraphe|liste|tableau_md|sous_titre|image", "heading_level": null, "document_id": null, "texte": "..."}}],
  "citations": ["1", "2"],
  "exigences_couvertes": [],
  "abstentions": ["..."]
}}

{history}

Contexte (extraits numérotés, avec l'expert qui les a trouvés) :
{context}

Abstentions déjà connues (aucune recherche ne les a couvertes, à mentionner) :
{abstentions}
"""

_EXIGENCES_SECTION_TEMPLATE = """
Exigences du DAO que CETTE section doit traiter explicitement — adresse-les
vraiment dans le texte rédigé, ne te contente pas de les lister :
{exigences_list}
Dans "exigences_couvertes", ne mets QUE les identifiants ci-dessus (copiés
EXACTEMENT) que le texte rédigé traite réellement. N'invente aucun id, et
n'en mets aucun si le texte ne traite en réalité aucune de ces exigences.
"""

_GROUNDING_STRICT = (
    "- Utilise UNIQUEMENT les extraits numérotés du contexte pour les faits.\n"
    "- Si une information manque, ajoute-la dans \"abstentions\", n'invente RIEN."
)

# §retour utilisateur : "tout ne peut pas être dans le patrimoine" — pour une
# PROPOSITION explicitement demandée (mot-clé "propose"/"suggère"/...), le
# patrimoine ne fournit parfois rien de directement exploitable, mais
# répondre uniquement par des abstentions n'aide personne. On autorise donc
# une structuration/narration plausible même sans source précise — MAIS
# jamais d'invention de FAIT VÉRIFIABLE spécifique à l'entreprise (chiffre,
# certification, date, nom de projet réel) : ça reste une réponse à un
# marché public, une fausse déclaration y a un vrai coût. Ce qui n'est pas
# dans le contexte et relève d'un fait vérifiable doit être marqué
# "[À COMPLÉTER : ...]" plutôt qu'inventé.
_GROUNDING_PROPOSAL = (
    "- C'est une PROPOSITION explicitement demandée : le patrimoine ne fournit pas\n"
    "  forcément de source précise ici, mais tu dois quand même produire un texte\n"
    "  concret et structuré (cadrage, méthodologie générale, organisation plausible\n"
    "  pour ce type de projet BTP) plutôt que de multiplier les abstentions.\n"
    "- INTERDICTION ABSOLUE d'inventer un FAIT VÉRIFIABLE spécifique à l'entreprise\n"
    "  (chiffre d'affaires, effectif, certification, date, nom de projet réel) sans\n"
    "  source dans le contexte — pour CES éléments précis (pas le reste du texte),\n"
    "  écris \"[À COMPLÉTER : ...]\" plutôt que d'inventer.\n"
    "- Ajoute dans \"abstentions\" une note explicite que ce texte est une PROPOSITION\n"
    "  à valider par un humain avant tout dépôt, pas une affirmation de fait établie."
)

_EXISTING_CONTENT_TEMPLATE = """
Cette section a DÉJÀ une version rédigée ci-dessous. La consigne ci-dessus
demande de l'ENRICHIR ou de la COMPLÉTER, PAS de repartir de zéro : garde le
contenu déjà validé, intègre l'ajout demandé de façon cohérente avec le
reste (même ton, pas de répétition de ce qui est déjà dit).

Version actuelle :
---
{existing_markdown}
---
"""


def _translate_citation_numbers(body: dict, aggregated: AggregatedContext) -> None:
    """Le modèle ne voit JAMAIS le vrai chunk_id (UUID) dans son contexte —
    seulement le numéro d'affichage [1], [2]... placé devant chaque extrait
    (aggregate.py). Lui demander de citer un "chunk_id" qu'il n'a
    structurellement aucun moyen de connaître faisait échouer la validation
    des citations presque systématiquement (bug réel identifié en creusant
    les échecs de génération) : le modèle citait alors le libellé affiché
    tel quel ("[1] p.389"), jamais un vrai id. On lui demande maintenant le
    NUMÉRO (qu'il voit réellement) et on le traduit ICI, en id réel, avant
    toute validation — `aggregated.citations[i]` est le chunk_id du
    numéro i+1 par construction (même ordre d'insertion dans aggregate())."""

    def _resolve(value: object) -> str | None:
        try:
            idx = int(str(value).strip().strip("[]."))
        except (TypeError, ValueError):
            return None
        if 1 <= idx <= len(aggregated.citations):
            return aggregated.citations[idx - 1]
        return None

    resolved_citations: list[str] = []
    for raw in body.get("citations") or []:
        real_id = _resolve(raw)
        if real_id and real_id not in resolved_citations:
            resolved_citations.append(real_id)
    body["citations"] = resolved_citations

    for bloc in body.get("blocs") or []:
        if isinstance(bloc, dict) and bloc.get("type") == "image" and bloc.get("document_id") is not None:
            real_id = _resolve(bloc["document_id"])
            if real_id:
                bloc["document_id"] = real_id


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
    exigences: list[dict] | None = None,
    existing_markdown: str | None = None,
    allow_proposal: bool = False,
) -> SectionGeneree:
    """Génère (et valide, avec retry borné) une section — jamais plus de
    MAX_ESSAIS appels LLM (garde-fou, même famille que max_iter CRAG).

    `exigences` : les exigences du DAO liées à cette section (table
    exigence_sections, § liaison exigences/sections) — chaque dict
    {"id", "libelle", "type"}. Injectées dans le prompt pour que la
    rédaction les traite VRAIMENT, pas juste un contexte patrimoine
    générique. `exigences_couvertes` renvoyé par le LLM est ensuite filtré
    pour ne garder que des ids réellement fournis ici — sans ça ce champ
    est une liste inventée sans aucune garantie (gap identifié en revue).

    `existing_markdown` : la version déjà rédigée, à fournir quand l'appelant
    a détecté une demande d'ENRICHISSEMENT plutôt qu'une régénération
    complète (ex. depuis la conversation, "ajoute un paragraphe sur..." —
    voir app.services.chat_pipeline._is_extend_request). Sans ce paramètre,
    chaque génération repart de zéro, ce qui surprenait l'utilisateur
    quand sa demande était en réalité d'AJOUTER à l'existant.

    `allow_proposal` : relâche la règle "n'invente rien" pour cette seule
    génération (§retour utilisateur : "tout ne peut pas être dans le
    patrimoine") — voir _GROUNDING_PROPOSAL pour les garde-fous qui restent
    absolus (jamais un fait vérifiable inventé). À réserver aux demandes où
    l'utilisateur a explicitement dit "propose"/"suggère" (voir
    app.workflow.nodes.route.is_proposal_request) — par défaut la rédaction
    reste strictement sourcée."""

    guidance = _ARCHETYPE_GUIDANCE.get(archetype, _DEFAULT_GUIDANCE)
    grounding_rule = _GROUNDING_PROPOSAL if allow_proposal else _GROUNDING_STRICT
    consigne_extra = f"Consigne complémentaire de l'utilisateur : {custom_instruction}" if custom_instruction else ""
    valid_exigence_ids = {str(e["id"]) for e in exigences} if exigences else set()
    exigences_section = ""
    if exigences:
        exigences_list = "\n".join(
            f"- [{e.get('type', '?').upper()}] {e['libelle']} (id={e['id']})" for e in exigences
        )
        exigences_section = _EXIGENCES_SECTION_TEMPLATE.format(exigences_list=exigences_list)
    existing_content_section = (
        _EXISTING_CONTENT_TEMPLATE.format(existing_markdown=existing_markdown) if existing_markdown else ""
    )
    prompt = _PROMPT.format(
        titre=titre,
        section_key=section_key,
        guidance=guidance,
        grounding_rule=grounding_rule,
        existing_content_section=existing_content_section,
        consigne_extra=consigne_extra,
        exigences_section=exigences_section,
        history=format_history(history) or "",
        context=aggregated.context_text,
        abstentions="\n".join(f"- {a}" for a in aggregated.abstentions) or "(aucune)",
    )

    last_error: Exception | None = None
    for essai in range(1, MAX_ESSAIS + 1):
        try:
            # num_ctx=8192 — sans lui, Ollama applique son défaut (2048
            # tokens) et tronque ce prompt EN SILENCE, souvent en coupant le
            # schéma JSON attendu en toute fin de prompt. Le contexte agrégé
            # est lui-même plafonné à 20000 caractères (aggregate.py) pour
            # rester dans cette marge une fois ajoutés instructions/
            # exigences/historique.
            # schema=... : décodage contraint par le VRAI schéma Pydantic,
            # pas juste format="json" (JSON valide mais forme libre) — sans
            # ça, un petit modèle local dérivait régulièrement vers une
            # structure inventée sans rapport (bug réel, creusé et confirmé
            # en isolant les échecs de génération). Voir ollama_llm.py.
            body = await asyncio.to_thread(
                partial(
                    ollama_generate_json,
                    prompt,
                    timeout=180,
                    num_ctx=8192,
                    schema=SectionGeneree.model_json_schema(),
                )
            )
        except Exception as exc:
            last_error = exc
            log.warning("generate_section — appel LLM échoué (essai %d) : %s", essai, exc)
            continue

        _translate_citation_numbers(body, aggregated)
        try:
            section = SectionGeneree.model_validate(body)
        except ValidationError as exc:
            last_error = exc
            log.warning("generate_section — JSON invalide (essai %d) : %s", essai, exc)
            prompt += f"\n\nERREUR précédente à corriger : {exc}\nRéponds à nouveau en JSON valide."
            continue

        errors = _validate(section, aggregated)
        if not errors:
            if valid_exigence_ids:
                section.exigences_couvertes = [
                    eid for eid in section.exigences_couvertes if eid in valid_exigence_ids
                ]
            else:
                section.exigences_couvertes = []
            section.is_proposal = allow_proposal
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
    if section.is_proposal:
        # Bandeau posé par le CODE, jamais laissé au seul bon vouloir du
        # LLM (qui reçoit bien la consigne de le mentionner dans les
        # abstentions, mais rien ne garantit qu'il s'y tienne) — un texte
        # non sourcé doit toujours être visuellement distinct d'un texte
        # patrimoine, avant même de lire le contenu.
        lines.append("> ⚠️ **Proposition non sourcée sur le patrimoine — à valider avant tout dépôt.**")
        lines.append("")
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

"""Nœud Superviseur / Router — §8, architecture_agentique_retrieval_generation.md.

1 seul appel LLM JSON contraint (température basse) qui fait TOUT en un
passage : classification d'intention, détection de question composée,
décomposition en sous-questions, routage vers les experts, estimation de
complexité par sous-question. Aucun agent séparé pour la décomposition
(§5.5) — c'est le même appel, le même schéma.

Repli déterministe si le LLM échoue ou sort un JSON invalide : on retombe
sur les règles mots-clés historiques (app.workflow.nodes.route) plutôt que
de bloquer tout le pipeline sur une panne de classification.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from app.models.pydantic import Complexite, Expert, Intent, SousQuestion, SuperviseurOutput
from app.services.chat_history import format_history
from app.services.ollama_llm import ollama_generate_json
from app.workflow.nodes.route import EXPORT_KEYWORDS, GEN_KEYWORDS
from app.workflow.nodes.route import is_extend_request as _is_extend_request
from app.workflow.nodes.route import is_proposal_request as _is_proposal_request
from app.workflow.nodes.route import route as _legacy_route

log = logging.getLogger("btp.superviseur")

MAX_SOUS_QUESTIONS = 4

_EXPERTS_DESC = """Experts disponibles (jamais un nom hors de cette liste) :
  - "juridique"  : clauses, pénalités, délais, RC/CCAP
  - "technique"  : spécifications, méthodologie, CCTP
  - "financier"  : chiffres exacts, DPGF/BPU
  - "graphe"     : relations entre entités (qui a fait quoi, quelle certif
                   couvre quelle exigence)
  - "patrimoine" : références, projets passés, CV, certifications"""

_PROMPT = """Tu es le routeur d'un système de recherche documentaire pour des
dossiers d'appels d'offres BTP. Tu ne réponds JAMAIS à la question de
l'utilisateur. Ton seul travail : classifier son message et, si nécessaire,
le découper en sous-questions de recherche.

Tu dois répondre EXCLUSIVEMENT en JSON, selon ce schéma strict :
{{
  "intent": "smalltalk" | "export" | "clarification_needed" | "hybrid_rag" | "run_section",
  "is_compound": boolean,
  "sous_questions": [
    {{"texte": string, "experts": [string], "complexite": "simple" | "complexe"}}
  ],
  "message_clarification": string ou null
}}

{experts}

Règles STRICTES (chacune ferme un cas d'erreur précis) :
R1. Décompose UNIQUEMENT si les parties de la question demandent des
    recherches INDÉPENDANTES (le résultat de l'une n'est pas nécessaire
    pour formuler l'autre). Sinon is_compound=false, 1 seule sous-question.
R2. Chaque texte de sous-question doit être COMPLET et AUTONOME : aucun
    pronom ni référence implicite sans le nommer explicitement.
R3. Maximum {max_sq} sous-questions. Si plus seraient nécessaires : regroupe,
    ou réponds intent="clarification_needed" avec message_clarification.
R4. is_compound=false → EXACTEMENT 1 sous-question. is_compound=true →
    ENTRE 2 ET {max_sq} sous-questions. Jamais 0, jamais 1 avec is_compound=true.
R5. Une comparaison/calcul/synthèse finale demandée N'EST PAS une
    sous-question de recherche — ne crée jamais de sous-question sans
    recherche factuelle propre.
R6. Si intent ∈ {{"smalltalk","export"}} : sous_questions=[] et
    message_clarification=null, TOUJOURS.
R7. Si intent="clarification_needed" : sous_questions=[] et
    message_clarification OBLIGATOIRE (jamais null).
R8. "complexite" s'évalue PAR sous-question : une question factuelle simple
    = "simple" (1 seule passe) ; plusieurs critères, entité rare, ou
    run_section = "complexe" (boucle de correction complète).
R9. "experts" PEUT être vide ([]) — UNIQUEMENT si le message de l'utilisateur
    (ou l'historique immédiat) contient DÉJÀ le contenu factuel spécifique
    nécessaire à CETTE sous-question précise. Dans le doute, NE PAS mettre
    experts=[] : une recherche redondante coûte peu, une génération privée
    d'information disponible coûte cher en confiance.
R10. Le champ "texte" de chaque sous-question DOIT être écrit en FRANÇAIS,
    même si tu raisonnes en anglais — ne traduis JAMAIS la question.

Historique :
{history}

Message de l'utilisateur : {question}
"""


def _fallback(query: str) -> SuperviseurOutput:
    """Repli déterministe : réutilise les règles mots-clés historiques."""
    legacy = _legacy_route({"query": query})
    intent = legacy.get("intent", "hybrid_rag")
    if intent in ("smalltalk", "export"):
        return SuperviseurOutput(intent=Intent(intent), is_compound=False, sous_questions=[])
    experts = [Expert.patrimoine]
    return SuperviseurOutput(
        intent=Intent(intent),
        is_compound=False,
        sous_questions=[SousQuestion(texte=query, experts=experts, complexite=Complexite.simple)],
    )


def run_superviseur(
    query_clean: str, history: list[dict] | None, *, raw_query: str | None = None
) -> SuperviseurOutput:
    """`raw_query` : le message TEL QUE tapé, avant `rewrite_query`. Les
    garde-fous mots-clés ci-dessous testent CE texte, pas `query_clean` —
    `rewrite_query` transforme délibérément un impératif ("Rédige...",
    "Exporte...") en phrase de recherche neutre pour le retrieval (son
    prompt le dit explicitement : "une PHRASE DE RECHERCHE, pas une réponse
    à la question"), ce qui efface justement le verbe d'action dont ces
    garde-fous ont besoin. Bug réel observé : "Rédige la présentation..."
    réécrit en une phrase sans "rédige" faisait passer le message au travers
    du garde-fou run_section."""
    query_clean = (query_clean or "").strip()
    guard_text = (raw_query or query_clean or "").strip()
    if not query_clean:
        return SuperviseurOutput(intent=Intent.smalltalk, is_compound=False, sous_questions=[])

    prompt = _PROMPT.format(
        experts=_EXPERTS_DESC,
        max_sq=MAX_SOUS_QUESTIONS,
        history=format_history(history) or "(aucun)",
        question=query_clean,
    )
    try:
        # num_ctx=4096 : l'historique de conversation peut grandir, sans
        # cette borne Ollama tronquerait en silence à son défaut (2048).
        body = ollama_generate_json(prompt, timeout=90, num_ctx=4096)
        output = SuperviseurOutput.model_validate(body)
    except (ValidationError, ValueError, TypeError) as exc:
        log.warning("Superviseur — JSON invalide, repli déterministe : %s", exc)
        return _fallback(query_clean)
    except Exception as exc:
        log.warning("Superviseur — appel LLM échoué, repli déterministe : %s", exc)
        return _fallback(query_clean)

    # Garde-fous appliqués côté code même si le LLM les a mal respectés —
    # ne jamais faire confiance aveuglément à la sortie d'un LLM (§8, R3/R4/R7).
    # Constat en test réel (llama3, modèle local modeste) : le JSON valide
    # côté Pydantic mais viole parfois la sémantique voulue (is_compound=true
    # avec 1 seule sous-question, clarification_needed avec sous_questions
    # non vides). On corrige plutôt que de faire confiance au flag du modèle.
    if len(output.sous_questions) > MAX_SOUS_QUESTIONS:
        log.warning("Superviseur — %d sous-questions > max, tronqué", len(output.sous_questions))
        output.sous_questions = output.sous_questions[:MAX_SOUS_QUESTIONS]

    lowered_query = guard_text.lower()
    if output.intent == Intent.export and not any(w in lowered_query for w in EXPORT_KEYWORDS):
        # intent="export" déclenche un TÉLÉCHARGEMENT silencieux côté client
        # (SSE export_ready) dès que ce message arrive — un faux positif
        # (observé sur un message aussi court que "pourquoi ?", un petit
        # modèle local le classe parfois export) surprend l'utilisateur avec
        # un fichier généré au lieu d'une réponse. Une vraie demande d'export
        # contient toujours un mot sans ambiguïté (export, télécharge, docx,
        # pdf...) — sans ça, on ne fait jamais confiance à la seule
        # classification du LLM pour une action aussi visible. Ce garde-fou
        # tourne AVANT celui de run_section ci-dessous : un faux "export" doit
        # pouvoir retomber sur "run_section" s'il en a le mot-clé, pas
        # s'arrêter à mi-chemin sur hybrid_rag.
        log.warning(
            "Superviseur — intent=export sans mot-clé explicite, requalifié hybrid_rag (message=%r)",
            guard_text[:80],
        )
        output.intent = Intent.hybrid_rag

    if output.intent not in (Intent.export, Intent.run_section) and (
        any(w in lowered_query for w in GEN_KEYWORDS)
        or _is_extend_request(guard_text)
        or _is_proposal_request(guard_text)
    ):
        # Même logique que le garde-fou export ci-dessus : "ajoute plus de
        # contenu" / "rédige en plus" sont des demandes de rédaction sans
        # ambiguïté lexicale, observées mal classées (parfois même en
        # "export", corrigé juste au-dessus) par ce petit modèle local — ne
        # pas laisser passer un faux négatif aussi facile à détecter
        # déterministiquement.
        log.warning(
            "Superviseur — intent=%s malgré un mot-clé de rédaction/enrichissement/proposition explicite, "
            "requalifié run_section (message=%r)",
            output.intent.value, guard_text[:80],
        )
        output.intent = Intent.run_section

    if output.intent == Intent.clarification_needed and output.sous_questions:
        # R7 : clarification_needed → sous_questions=[] TOUJOURS. Si le modèle
        # en a quand même produit, c'est plus probablement une mauvaise
        # classification qu'un vrai besoin de clarification — ne pas bloquer
        # l'utilisateur pour rien, requalifier en hybrid_rag.
        log.warning("Superviseur — clarification_needed avec sous_questions, requalifié hybrid_rag")
        output.intent = Intent.hybrid_rag

    if output.intent in (Intent.smalltalk, Intent.export, Intent.clarification_needed):
        output.sous_questions = []
    else:
        output.message_clarification = None

    if output.intent == Intent.clarification_needed and not output.message_clarification:
        output.message_clarification = (
            "Pouvez-vous préciser votre demande ? Elle comporte trop de critères "
            "distincts pour une seule recherche."
        )

    if output.intent in (Intent.hybrid_rag, Intent.run_section) and not output.sous_questions:
        # Le modèle a choisi une intention qui exige une recherche mais n'a
        # produit aucune sous-question — repli sur la requête telle quelle.
        output.sous_questions = [
            SousQuestion(texte=query_clean, experts=[Expert.patrimoine], complexite=Complexite.simple)
        ]

    # is_compound DÉRIVÉ du nombre réel de sous-questions plutôt que du flag
    # du modèle (R4) : garantit la cohérence par construction.
    output.is_compound = len(output.sous_questions) > 1
    return output

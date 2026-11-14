"""Nœud route : règles rapides. Pas d'agent autonome."""

# Partagé avec app.workflow.nodes.superviseur (garde-fous anti-faux-positif
# sur les intents décidés par le LLM) et app.services.chat_pipeline
# (détection d'une demande d'enrichissement de section) — regroupés ici,
# module sans dépendance, pour éviter tout import circulaire.
EXPORT_KEYWORDS = ("export", "exporte", "télécharge", "telecharge", "docx", "pdf du dossier")

GEN_KEYWORDS = (
    "génère",
    "genere",
    "rédige",
    "redige",
    "écris la section",
    "ecris la section",
    "ajoute au document",
    "ajoute ça au document",
    "ajoute ca au document",
    "mémoire technique",
    "memoire technique",
)

# Signale une demande d'ENRICHISSEMENT d'une section déjà rédigée plutôt
# qu'une régénération complète (ex. "ajoute plus de contenu", "rédige en
# plus") — observé en usage réel : ces messages étaient mal classés (parfois
# même en "export", voir superviseur.py) et, même correctement routés,
# produisaient une section repartie de zéro au lieu d'étendre l'existant.
EXTEND_KEYWORDS = (
    "ajoute",
    "rajoute",
    "en plus",
    "plus de contenu",
    "complète",
    "complete",
    "enrichis",
    "enrichi",
    "continue",
)


def is_extend_request(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in EXTEND_KEYWORDS)


# Signale une demande de PROPOSITION plutôt qu'une rédaction strictement
# sourcée : tout n'est pas dans le patrimoine (§ retour utilisateur), et le
# garde-fou "n'invente RIEN" de generate_section (utile pour ne jamais
# fabriquer un fait vérifiable sur l'entreprise) empêchait aussi de proposer
# un texte de cadrage/structuration quand aucune source précise n'existe.
# Ce mot-clé relâche cette contrainte pour CETTE génération uniquement — et
# uniquement pour la structuration/le narratif, jamais pour les faits
# vérifiables (chiffres, certifications...), voir generate_section.py.
PROPOSAL_KEYWORDS = (
    "propose",
    "proposition",
    "suggère",
    "suggere",
    "suggestion",
    "imagine",
)


def is_proposal_request(text: str) -> bool:
    lowered = text.lower()
    return any(w in lowered for w in PROPOSAL_KEYWORDS)


def route(state: dict) -> dict:
    text = (state.get("query") or "").strip()
    if not text:
        messages = state.get("messages") or []
        if messages:
            last = messages[-1]
            text = last.get("content", "") if isinstance(last, dict) else str(last)
    lowered = text.lower()
    if any(w in lowered for w in EXPORT_KEYWORDS):
        intent = "export"
    elif any(w in lowered for w in GEN_KEYWORDS) or is_extend_request(text):
        intent = "run_section"
    elif not text.strip() or lowered.strip() in {"bonjour", "hello", "salut", "coucou"}:
        intent = "smalltalk"
    else:
        intent = "hybrid_rag"
    return {**state, "intent": intent, "query": text}

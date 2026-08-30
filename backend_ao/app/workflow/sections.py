"""Plan type du mémoire V1 + détection de section depuis la consigne."""

DEFAULT_OUTLINE: list[tuple[str, int, str]] = [
    ("presentation", 1, "Présentation de l'entreprise"),
    ("moyens_humains", 1, "Moyens humains"),
    ("references", 1, "Références et projets similaires"),
    ("methodologie", 1, "Méthodologie et organisation"),
    ("planning", 1, "Planning et délais"),
]

# V2 — §10 : spécialisation déterministe du prompt de génération. Lookup
# fixe pour le canevas par défaut ; un plan extrait dynamiquement (§9,
# extract_outline) classe son propre archetype au moment de l'extraction.
ARCHETYPE_BY_KEY: dict[str, str] = {
    "presentation": "institutionnelle",
    "moyens_humains": "factuelle",
    "moyens_materiels": "factuelle",
    "references": "factuelle",
    "methodologie": "narrative",
    "comprehension": "narrative",
    "planning": "factuelle",
    "qse": "conformite",
}
DEFAULT_ARCHETYPE = "factuelle"


def archetype_for_key(key: str) -> str:
    return ARCHETYPE_BY_KEY.get(key, DEFAULT_ARCHETYPE)

_ALL = (
    "tout le mémoire",
    "tout le memoire",
    "le mémoire complet",
    "le memoire complet",
    "toutes les sections",
    "rédige le dossier",
    "redige le dossier",
    "génère le mémoire",
    "genere le memoire",
)

_MAP = (
    (("moyen", "personnel", "équipe", "equipe", "effectif"), "moyens_humains"),
    (("référence", "reference", "chantier similaire", "projet similaire"), "references"),
    (("méthod", "method", "organisation", "phasa"), "methodologie"),
    (("planning", "délai", "delai", "calendrier"), "planning"),
    (("présentation", "presentation", "entreprise", "société", "societe"), "presentation"),
)


def pick_section(query: str) -> tuple[str, str, bool]:
    lowered = query.lower()
    if any(w in lowered for w in _ALL):
        return "presentation", "Présentation de l'entreprise", True
    titles = {k: t for k, _lvl, t in DEFAULT_OUTLINE}
    for words, key in _MAP:
        if any(w in lowered for w in words):
            return key, titles[key], False
    return "notes_travail", "Notes de travail", False

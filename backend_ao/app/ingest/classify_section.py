"""Classification dynamique de section_type (§3.1, Nouvelle_Architecture/
architecture_agentique_retrieval_generation.md).

Deux couches :
  1. Heuristique (mots-clés sur les titres canoniques d'un AO français) —
     quasi gratuite, tourne sur TOUS les parents.
  2. LLM JSON contraint — uniquement pour les parents où la couche 1 est
     muette (pas limité à un sous-ensemble, contrairement à extract_graph).

section_type est un signal DOUX pour le routage des experts (jamais un
filtre bloquant) : une classification ratée s'auto-corrige dans la boucle
CRAG (Ambigu/Incorrect → élargir en lâchant ce filtre, §5.2).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

from app.config import get_settings

log = logging.getLogger("btp.classify_section")

SECTION_TYPES = ("rc", "ccap", "cctp", "dpgf", "bpu", "memoire", "reference", "autre")

# Couche 1 — titres canoniques d'un AO français (Code de la commande publique),
# déjà cités dans l'état de l'art du mémoire (test.md §1.2.1).
_HEURISTICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("rc", re.compile(r"r[eè]glement\s+de\s+(la\s+)?consultation|\bRC\b", re.IGNORECASE)),
    (
        "ccap",
        re.compile(
            r"cahier\s+des\s+clauses\s+administratives\s+particuli[eè]res|\bCCAP\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cctp",
        re.compile(
            r"cahier\s+des\s+clauses\s+techniques\s+particuli[eè]res|\bCCTP\b",
            re.IGNORECASE,
        ),
    ),
    (
        "dpgf",
        re.compile(
            r"d[eé]composition\s+du\s+prix\s+global\s+et\s+forfaitaire|\bDPGF\b",
            re.IGNORECASE,
        ),
    ),
    ("bpu", re.compile(r"bordereau\s+des\s+prix\s+unitaires|\bBPU\b", re.IGNORECASE)),
    (
        "memoire",
        re.compile(r"m[eé]moire\s+technique|m[eé]moire\s+justificatif", re.IGNORECASE),
    ),
    (
        "reference",
        re.compile(
            r"r[eé]f[eé]rences?\s+chantier|attestation\s+de\s+bonne\s+ex[eé]cution",
            re.IGNORECASE,
        ),
    ),
)

_HEAD_SAMPLE_CHARS = 200

_LLM_PROMPT = """Tu classes un extrait de dossier d'appel d'offres BTP dans UNE catégorie.
Catégories autorisées, choisis UNIQUEMENT parmi : rc, ccap, cctp, dpgf, bpu, memoire, reference, autre.
Réponds UNIQUEMENT en JSON : {{"section_type": "..."}}
Texte :
"""


def classify_section_type_heuristic(heading_path: str | None, text: str) -> str | None:
    """Couche 1 — quasi gratuite, aucun appel réseau. Retourne None si aucun
    mot-clé canonique n'est trouvé (auquel cas la couche 2 prend le relais)."""

    sample = f"{heading_path or ''}\n{(text or '')[:_HEAD_SAMPLE_CHARS]}"
    for section_type, pattern in _HEURISTICS:
        if pattern.search(sample):
            return section_type
    return None


def classify_section_type_llm(text: str) -> str | None:
    """Couche 2 — 1 appel LLM JSON contraint, seulement si la couche 1 échoue.
    Ne lève jamais : une classification manquée reste `None` (signal doux)."""

    s = get_settings()
    payload = json.dumps(
        {
            "model": s.llm_model,
            "prompt": _LLM_PROMPT + text[:2000],
            "stream": False,
            "format": "json",
        }
    ).encode()
    req = urllib.request.Request(
        f"{s.ollama_base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read().decode())
        body = json.loads(raw.get("response") or "{}")
        value = str(body.get("section_type", "")).strip().lower()
        return value if value in SECTION_TYPES else None
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as exc:
        log.warning("classify_section_type_llm — échec, section_type laissé vide : %s", exc)
        return None


def classify_section_type(heading_path: str | None, text: str) -> tuple[str | None, str]:
    """Retourne (section_type, méthode). méthode ∈ {"heuristic", "llm", "none"}."""

    heuristic = classify_section_type_heuristic(heading_path, text)
    if heuristic is not None:
        return heuristic, "heuristic"
    llm_result = classify_section_type_llm(text)
    if llm_result is not None:
        return llm_result, "llm"
    return None, "none"

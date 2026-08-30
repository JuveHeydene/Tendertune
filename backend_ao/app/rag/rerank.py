"""Rerank — §4.5.

Cible documentée : BGE-reranker-v2-m3 (cross-encoder). Non câblé pour l'instant
: `sentence-transformers`/`torch` sont déjà dépendances du projet mais
l'environnement de dev a un conflit cuDNN 8 (Paddle) vs cuDNN 9 (torch) déjà
documenté dans JOURNAL.md ("Étape 2") — retenter cette installation ici
rouvrirait ce conflit connu sans rapport avec la tâche en cours.

En attendant : un reranking lexical réel (pas un stub qui tronque juste la
liste) — recouvrement de tokens requête/chunk, pondéré avec le score RRF déjà
calculé. Fait mieux que "premiers du RRF" sur les cas déjà documentés dans
RAG-07 §5 (un chunk thématiquement proche mais qui ne contient aucun mot de
la question précise est pénalisé). Chemin de mise à niveau : remplacer
`_lexical_overlap` par un vrai cross-encoder quand l'environnement le permet,
sans changer la signature de `rerank()`.
"""

from __future__ import annotations

import re

from app.config import get_settings

_TOKEN_RE = re.compile(r"[a-zàâäéèêëïîôöùûüç0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "les", "des", "une", "que", "qui", "est", "dans", "pour", "avec", "sur",
    "par", "aux", "ces", "son", "ses", "ont", "été", "être", "dont", "cette",
    "nous", "vous", "ils", "elle", "leur", "plus", "tout", "sont",
}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if t.lower() not in _STOPWORDS}


def _lexical_overlap(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokens(text)
    if not text_tokens:
        return 0.0
    return len(query_tokens & text_tokens) / len(query_tokens)


def rerank(query: str, nodes: list[dict], top_n: int = 8) -> list[dict]:
    """Reclasse une liste déjà courte (Top-50 fusionné) — jamais tout le
    corpus. Score final = mélange du rang RRF (déjà une bonne fusion
    dense+sparse) et du recouvrement lexical direct avec la question."""

    s = get_settings()
    _ = s.rerank_model, s.device  # cible documentée, non utilisée ici (voir docstring)

    if not nodes:
        return []
    query_tokens = _tokens(query)
    rrf_scores = [n.get("rrf_score", n.get("score", 0.0)) for n in nodes]
    max_rrf = max(rrf_scores) or 1.0

    scored = []
    for node, rrf in zip(nodes, rrf_scores, strict=True):
        overlap = _lexical_overlap(query_tokens, node.get("text", ""))
        rerank_score = 0.5 * (rrf / max_rrf) + 0.5 * overlap
        enriched = dict(node)
        enriched["rerank_score"] = rerank_score
        scored.append(enriched)

    scored.sort(key=lambda n: n["rerank_score"], reverse=True)
    return scored[:top_n]

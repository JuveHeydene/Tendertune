"""Nœud rewrite — résout la déixis avant tout retrieval (§4.1, RAG-08 §3).

1 appel LLM JSON contraint. En cas d'échec (Ollama injoignable, JSON invalide),
repli déterministe : on renvoie le texte brut tel quel plutôt que de bloquer
tout le pipeline sur une étape qui n'est qu'une amélioration de recall.
"""

from __future__ import annotations

import logging

from app.services.chat_history import format_history
from app.services.ollama_llm import ollama_generate_json

log = logging.getLogger("btp.rewrite")

_PROMPT = """Tu réécris la question d'un utilisateur pour la rendre autonome,
sans te baser sur l'historique de conversation pour la comprendre.

Règles STRICTES :
- Remplace "ça", "le dernier", "celui-ci"... par ce qu'ils désignent, déduit
  de l'historique.
- Ne CASSE JAMAIS un identifiant exact (référence de marché, article, sigle).
- Produis une PHRASE DE RECHERCHE, pas une réponse à la question.
- Si la question est déjà autonome, renvoie-la telle quelle.

Réponds UNIQUEMENT en JSON : {{"query_clean": "..."}}

Historique :
{history}

Question brute : {question}
"""


def rewrite_query(question: str, history: list[dict] | None) -> str:
    question = (question or "").strip()
    if not question:
        return question
    try:
        prompt = _PROMPT.format(history=format_history(history) or "(aucun)", question=question)
        body = ollama_generate_json(prompt, timeout=60)
        clean = str(body.get("query_clean") or "").strip()
        if clean:
            return clean
    except Exception as exc:
        log.warning("rewrite_query — échec, texte brut conservé : %s", exc)
    return question

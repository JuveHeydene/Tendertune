"""grade_context — cœur de CRAG (§5.3).

Hybride seuil + LLM-juge en zone grise (décision validée, tableau §7 point
#3) : le seuil est gratuit (déjà calculé par le reranker) et suffit pour les
cas francs ; le LLM-juge ne coûte un appel que dans la zone ambiguë — même
principe Adaptive qu'au niveau de la question (§5.1), appliqué un cran plus
bas dans le grading lui-même.
"""

from __future__ import annotations

import logging

from app.models.pydantic import Grade
from app.services.ollama_llm import ollama_generate_json

log = logging.getLogger("btp.grading")

SEUIL_CORRECT = 0.7
SEUIL_INCORRECT = 0.3

_JUGE_PROMPT = """Tu évalues si un contexte documentaire permet de répondre à
une question. Réponds UNIQUEMENT en JSON : {{"grade": "correct"|"ambigu"|"incorrect"}}

- "correct" : le contexte permet de répondre précisément à la question.
- "ambigu" : le contexte est lié au sujet mais insuffisant ou incertain.
- "incorrect" : le contexte ne répond pas à la question, même s'il semble proche.

Question : {query}

Contexte :
{context}
"""


def _top_score(chunks: list[dict]) -> float:
    if not chunks:
        return 0.0
    return max(c.get("rerank_score", c.get("score", 0.0)) for c in chunks)


def grade_context(query: str, chunks: list[dict]) -> tuple[Grade, str]:
    """Retourne (grade, method). method ∈ {"seuil", "llm_juge"}."""

    if not chunks:
        return Grade.incorrect, "seuil"

    top = _top_score(chunks)
    if top >= SEUIL_CORRECT:
        return Grade.correct, "seuil"
    if top < SEUIL_INCORRECT:
        return Grade.incorrect, "seuil"

    # Zone grise (RAG-07 §5 : un chunk "thématiquement proche" peut avoir un
    # score moyen sans répondre à la question précise) — 1 seul appel LLM ici.
    try:
        context = "\n\n".join(f"[{i}] {c.get('text', '')[:1500]}" for i, c in enumerate(chunks[:5], 1))
        body = ollama_generate_json(_JUGE_PROMPT.format(query=query, context=context), timeout=60)
        value = str(body.get("grade", "")).strip().lower()
        if value in ("correct", "ambigu", "incorrect"):
            return Grade(value), "llm_juge"
    except Exception as exc:
        log.warning("grade_context — LLM-juge indisponible, repli Ambigu : %s", exc)
    return Grade.ambigu, "llm_juge"

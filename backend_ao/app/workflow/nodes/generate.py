"""Nœud generate : prompts Markdown + Ollama."""

from __future__ import annotations

from app.services.chat_history import format_history
from app.services.ollama_llm import ollama_generate
from app.workflow.sections import pick_section

_MD_RULES = (
    "Réponds en **Markdown** (titres ##, listes, tableaux Markdown si utile).\n"
    "Pas de titre H1 (#). Pas d'invention de montants, SIRET ou dates.\n"
)


def _context_block(retrieved: list) -> str:
    if not retrieved:
        return "(aucun extrait indexé pour ce tenant — répondre prudemment, sans inventer de chiffres.)"
    parts = []
    for i, hit in enumerate(retrieved, start=1):
        page = hit.get("page") or "?"
        head = hit.get("heading_path") or ""
        parts.append(f"[{i}] p.{page} {head}\n{(hit.get('text') or '')[:12000]}")
    return "\n\n".join(parts)


def build_prompt(state: dict) -> tuple[str, dict]:
    intent = state.get("intent") or "hybrid_rag"
    query = state.get("query") or ""
    retrieved = state.get("retrieved") or []
    history = format_history(state.get("history"))
    ctx = _context_block(retrieved)
    extra: dict = {}
    if intent == "run_section":
        key, title, all_flag = pick_section(query)
        extra = {
            "section_key": key,
            "section_title": title,
            "generate_all": all_flag,
        }
        prompt = (
            "Tu es rédacteur d'un mémoire technique d'appel d'offres BTP (français, ton professionnel).\n"
            f"Section : {title}.\n"
            f"{_MD_RULES}"
            "Utilise UNIQUEMENT les extraits. Si une info manque, écris [à compléter].\n"
            f"{history}"
            f"Consigne :\n{query}\n\nExtraits :\n{ctx}\n\nRédige la section en Markdown :"
        )
        return prompt, extra
    prompt = (
        "Tu es un assistant BTP pour préparer un dossier d'appel d'offres. Français.\n"
        f"{_MD_RULES}"
        "Réponds à partir des extraits et de l'historique. Cite [1], [2] quand tu t'appuies sur eux.\n"
        "Si les extraits ne suffisent pas, dis-le.\n"
        f"{history}"
        f"Question :\n{query}\n\nExtraits :\n{ctx}\n\nRéponse Markdown :"
    )
    return prompt, {}


def generate(state: dict) -> dict:
    intent = state.get("intent") or "hybrid_rag"
    query = state.get("query") or ""
    retrieved = state.get("retrieved") or []
    prompt, extra = build_prompt(state)
    answer = ollama_generate(prompt)
    out = {**state, "answer": answer, **extra}
    if intent != "run_section":
        out["citations"] = [
            {"chunk_id": h.get("chunk_id"), "page": h.get("page"), "score": h.get("score")}
            for h in retrieved[:6]
        ]
    elif "section_key" not in extra:
        key, title, all_flag = pick_section(query)
        out["section_key"] = key
        out["section_title"] = title
        out["generate_all"] = all_flag
    return out

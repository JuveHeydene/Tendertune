"""Historique conversation injecté dans les prompts LLM."""

from __future__ import annotations


def format_history(messages: list[dict] | None, *, max_turns: int = 8) -> str:
    """Formate les derniers échanges user/assistant pour le contexte Ollama."""
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages[-max_turns * 2 :]:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        label = "Utilisateur" if role == "user" else "Assistant"
        content = (m.get("content") or "").strip()
        meta = m.get("meta") or {}
        if role == "assistant" and meta.get("markdown"):
            md = str(meta["markdown"])
            content = md if len(content) < 40 else f"{content}\n{md[:400]}"
        if meta.get("upload") and meta.get("filename"):
            content = f"[Document déposé : {meta['filename']}] {content}".strip()
        if not content:
            continue
        if len(content) > 700:
            content = content[:700] + "…"
        lines.append(f"{label} : {content}")
    if not lines:
        return ""
    return "Historique récent de la conversation :\n" + "\n".join(lines) + "\n\n"

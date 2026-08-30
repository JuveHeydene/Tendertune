"""Nœud route : règles rapides. Pas d'agent autonome."""


def route(state: dict) -> dict:
    text = (state.get("query") or "").strip()
    if not text:
        messages = state.get("messages") or []
        if messages:
            last = messages[-1]
            text = last.get("content", "") if isinstance(last, dict) else str(last)
    lowered = text.lower()
    export_w = ("export", "exporte", "télécharge", "telecharge", "docx", "pdf du dossier")
    gen_w = (
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
    if any(w in lowered for w in export_w):
        intent = "export"
    elif any(w in lowered for w in gen_w):
        intent = "run_section"
    elif not text.strip() or lowered.strip() in {"bonjour", "hello", "salut", "coucou"}:
        intent = "smalltalk"
    else:
        intent = "hybrid_rag"
    return {**state, "intent": intent, "query": text}

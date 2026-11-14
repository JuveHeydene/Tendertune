"""Appel Ollama /api/generate (texte ou flux)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator

from app.config import get_settings

log = logging.getLogger("btp.llm")


def ollama_generate(prompt: str, *, timeout: int = 180, num_ctx: int | None = None) -> str:
    return "".join(ollama_generate_stream(prompt, timeout=timeout, num_ctx=num_ctx))


def ollama_generate_json(
    prompt: str, *, timeout: int = 120, num_ctx: int | None = None, schema: dict | None = None
) -> dict:
    """Appel JSON contraint côté Ollama — utilisé par le Superviseur, le
    rewrite, le grading LLM-juge, l'extraction d'entités de requête (V2) et
    generate_section. Ne lève jamais côté JSON invalide : retourne {} et
    laisse l'appelant décider du repli déterministe.

    `num_ctx` : sans lui, Ollama applique SA valeur par défaut (souvent 2048
    tokens), potentiellement bien en-dessous des 8192 supportés par le modèle
    (llama.context_length) — un prompt plus long serait tronqué en silence.
    À préciser explicitement dès qu'un appelant envoie un texte volumineux
    (ex. extraction par lots, extract_structure.py).

    `schema` : passer un vrai schéma JSON (ex. `MonModelePydantic.
    model_json_schema()`) plutôt que de laisser au défaut `format="json"` —
    Ollama (>=0.5, confirmé fonctionnel en 0.16.2) contraint alors le
    DÉCODAGE token par token pour qu'il ne puisse PHYSIQUEMENT PAS produire
    une structure hors schéma (champs manquants/en trop, mauvais type,
    valeurs d'enum invalides...). `format="json"` seul garantit juste du
    JSON syntaxiquement valide, PAS la forme attendue — un petit modèle
    local dérive alors régulièrement vers une structure sans rapport (bug
    réel identifié : la génération de section échouait à répétition sur des
    champs inventés comme "meilleur_expert" au lieu du schéma demandé)."""
    s = get_settings()
    url = f"{s.ollama_base_url.rstrip('/')}/api/generate"
    body_dict: dict = {"model": s.llm_model, "prompt": prompt, "stream": False, "format": schema or "json"}
    if num_ctx is not None:
        body_dict["options"] = {"num_ctx": num_ctx}
    payload = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama injoignable ({url}) : {exc}") from exc
    body = raw.get("response") or "{}"
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        log.warning("ollama_generate_json — réponse non-JSON, {} renvoyé : %r", body[:200])
        return {}


def ollama_generate_stream(prompt: str, *, timeout: int = 180, num_ctx: int | None = None) -> Iterator[str]:
    """`num_ctx` : ce paramètre n'existait pas ici avant — cette fonction
    alimente la réponse conversationnelle normale en streaming (chat_pipeline
    .py, intent hybrid_rag), qui embarque le contexte agrégé complet. Sans
    borne, Ollama tronquait en silence à son défaut (2048 tokens) exactement
    comme pour generate_section.py (voir ce fichier pour le détail du bug)."""
    s = get_settings()
    url = f"{s.ollama_base_url.rstrip('/')}/api/generate"
    body_dict: dict = {"model": s.llm_model, "prompt": prompt, "stream": True}
    if num_ctx is not None:
        body_dict["options"] = {"num_ctx": num_ctx}
    payload = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    log.info("Ollama stream DÉBUT model=%s prompt_car=%s", s.llm_model, len(prompt))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = chunk.get("response") or ""
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama injoignable ({url}) : {exc}") from exc
    log.info("Ollama stream FIN")

"""Appel Ollama /api/generate (texte ou flux)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Iterator

from app.config import get_settings

log = logging.getLogger("btp.llm")


def ollama_generate(prompt: str, *, timeout: int = 180) -> str:
    return "".join(ollama_generate_stream(prompt, timeout=timeout))


def ollama_generate_stream(prompt: str, *, timeout: int = 180) -> Iterator[str]:
    s = get_settings()
    url = f"{s.ollama_base_url.rstrip('/')}/api/generate"
    payload = json.dumps(
        {"model": s.llm_model, "prompt": prompt, "stream": True}
    ).encode()
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

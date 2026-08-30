"""Embeddings Ollama + upsert Qdrant (dense uniquement en V1)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.config import get_settings
from app.ingest.chunk import ChunkDraft

log = logging.getLogger("btp.embed")

NOMIC_DIM = 768


def ensure_collection() -> QdrantClient:
    s = get_settings()
    client = QdrantClient(url=s.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        log.info("création collection Qdrant %s dim=%s", s.qdrant_collection, NOMIC_DIM)
        client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=VectorParams(size=NOMIC_DIM, distance=Distance.COSINE),
        )
    return client


def embed_texts(texts: list[str], *, quiet: bool = False) -> list[list[float]]:
    s = get_settings()
    vectors = []
    if not quiet:
        log.info("Ollama embeddings : %s textes à envoyer", len(texts))
    for i, text in enumerate(texts):
        if not quiet:
            log.info("Ollama embedding DÉBUT %s/%s", i + 1, len(texts))
        payload = json.dumps({"model": s.embed_model, "prompt": text[:8000]}).encode()
        req = urllib.request.Request(
            f"{s.ollama_base_url.rstrip('/')}/api/embeddings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        url = f"{s.ollama_base_url.rstrip('/')}/api/embeddings"
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(
                f"Ollama HTTP {exc.code} {url} model={s.embed_model} : {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama injoignable ({url}) model={s.embed_model} — "
                f"ollama serve + ollama pull {s.embed_model} ? détail={exc}"
            ) from exc
        vec = body.get("embedding")
        if not vec:
            raise RuntimeError("Ollama n’a pas renvoyé d’embedding — modèle nomic-embed-text tiré ?")
        if not quiet:
            log.info("Ollama embedding FIN %s/%s dim=%s", i + 1, len(texts), len(vec))
        vectors.append(vec)
    if not quiet:
        log.info("Ollama embeddings : tous les vecteurs reçus (%s)", len(vectors))
    return vectors


def upsert_chunks(
    *,
    client: QdrantClient,
    tenant_id: UUID,
    document_id: UUID,
    doc_role: str,
    chunks: list[ChunkDraft],
    vectors: list[list[float]],
) -> None:
    s = get_settings()
    points = []
    for ch, vec in zip(chunks, vectors, strict=True):
        points.append(
            PointStruct(
                id=str(ch.id),
                vector=vec,
                payload={
                    "chunk_id": str(ch.id),
                    "document_id": str(document_id),
                    "tenant_id": str(tenant_id),
                    "doc_role": doc_role,
                    "heading_path": ch.heading_path,
                    "page": ch.page,
                    "page_group": (ch.extra or {}).get("page_group"),
                    "parent_id": str(ch.parent_id) if ch.parent_id else None,
                    "text": ch.text[:2000],
                },
            )
        )
    log.info("Qdrant upsert DÉBUT collection=%s n=%s", s.qdrant_collection, len(points))
    client.upsert(collection_name=s.qdrant_collection, points=points)
    log.info("Qdrant upsert FIN collection=%s", s.qdrant_collection)

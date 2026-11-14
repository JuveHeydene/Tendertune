"""Embeddings Ollama + upsert Qdrant (dense uniquement en V1)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import get_settings
from app.ingest.chunk import ChunkDraft

log = logging.getLogger("btp.embed")

def ensure_collection() -> QdrantClient:
    s = get_settings()
    client = QdrantClient(url=s.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        log.info("création collection Qdrant %s dim=%s", s.qdrant_collection, s.embed_dim)
        client.create_collection(
            collection_name=s.qdrant_collection,
            vectors_config=VectorParams(size=s.embed_dim, distance=Distance.COSINE),
        )
        return client
    # Collection créée avec un autre modèle d'embedding : on refuse d'y mélanger
    # des vecteurs d'une autre dimension plutôt que d'échouer au premier upsert.
    existing = client.get_collection(s.qdrant_collection).config.params.vectors.size
    if existing != s.embed_dim:
        raise RuntimeError(
            f"Collection Qdrant {s.qdrant_collection} en dim={existing}, mais EMBED_MODEL={s.embed_model} "
            f"attend EMBED_DIM={s.embed_dim} — supprimer la collection (ou changer QDRANT_COLLECTION) puis réindexer."
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
            raise RuntimeError(f"Ollama n’a pas renvoyé d’embedding — modèle {s.embed_model} tiré ?")
        if not quiet:
            log.info("Ollama embedding FIN %s/%s dim=%s", i + 1, len(texts), len(vec))
        vectors.append(vec)
    if not quiet:
        log.info("Ollama embeddings : tous les vecteurs reçus (%s)", len(vectors))
    return vectors


def delete_by_document(client: QdrantClient, document_id: UUID) -> None:
    """Supprime tous les points d'un document AVANT réindexation.

    Bug corrigé : les chunks Postgres d'un document sont supprimés puis
    recréés avec de NOUVEAUX id à chaque ré-ingestion (app/workers/ingest.py),
    mais rien ne supprimait les anciens points Qdrant correspondants — une
    relance (ré-ingestion manuelle, reprise après échec) laissait donc des
    vecteurs orphelins, dupliquant le contenu en recherche."""
    s = get_settings()
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        return
    client.delete(
        collection_name=s.qdrant_collection,
        points_selector=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=str(document_id)))]),
    )


def upsert_chunks(
    *,
    client: QdrantClient,
    tenant_id: UUID,
    document_id: UUID,
    doc_role: str,
    chunks: list[ChunkDraft],
    vectors: list[list[float]],
    section_types: dict | None = None,
    dossier_id: UUID | None = None,
) -> None:
    """`section_types` : {chunk_id: section_type|None}, calculé une fois par
    parent et propagé à ses enfants (§3.1) — filtre DOUX côté retrieval (§4.4).
    `dossier_id` : requis si doc_role="annexe" (§1.5), pour le scope-dossier."""
    s = get_settings()
    section_types = section_types or {}
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
                    "section_type": section_types.get(ch.id),
                    "dossier_id": str(dossier_id) if dossier_id else None,
                },
            )
        )
    log.info("Qdrant upsert DÉBUT collection=%s n=%s", s.qdrant_collection, len(points))
    client.upsert(collection_name=s.qdrant_collection, points=points)
    log.info("Qdrant upsert FIN collection=%s", s.qdrant_collection)

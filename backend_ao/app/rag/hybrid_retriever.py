"""Recherche dense Qdrant (V1) : patrimoine + DAO archives, même tenant."""

from __future__ import annotations

import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchAny, MatchValue

from app.config import get_settings
from app.ingest.index_qdrant import embed_texts
from app.rag.page_context import expand_hits_with_page_parents

log = logging.getLogger("btp.rag")

ALLOWED_ROLES = ["patrimoine", "dao_archive"]


def retrieve_hybrid(query: str, *, tenant_id: UUID, top_k: int = 8) -> list[dict]:
    s = get_settings()
    log.info("RAG retrieve DÉBUT tenant=%s top_k=%s", tenant_id, top_k)
    client = QdrantClient(url=s.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        log.info("RAG retrieve FIN — collection absente")
        return []
    vector = embed_texts([query[:8000]], quiet=True)[0]
    hits = _search(client, s.qdrant_collection, vector, tenant_id, ALLOWED_ROLES, top_k)
    if not hits:
        log.info("RAG : 0 hit filtré — repli sans filtre de rôle")
        hits = _search(client, s.qdrant_collection, vector, tenant_id, None, top_k)
    hits = expand_hits_with_page_parents(hits)
    log.info("RAG retrieve FIN n=%s", len(hits))
    return hits


def _search(client, collection: str, vector, tenant_id: UUID, roles: list[str] | None, top_k: int):
    must = [
        FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id))),
    ]
    if roles:
        must.append(FieldCondition(key="doc_role", match=MatchAny(any=roles)))
    response = client.query_points(
        collection_name=collection,
        query=vector,
        query_filter=Filter(must=must),
        limit=top_k,
        with_payload=True,
    )
    out = []
    for hit in response.points:
        payload = hit.payload or {}
        out.append(
            {
                "chunk_id": payload.get("chunk_id") or str(hit.id),
                "document_id": payload.get("document_id"),
                "score": float(hit.score or 0),
                "page": payload.get("page"),
                "page_group": payload.get("page_group"),
                "heading_path": payload.get("heading_path"),
                "doc_role": payload.get("doc_role"),
                "text": payload.get("text") or "",
            }
        )
    return out

"""Recherche dense Qdrant : V1 (retrieve_hybrid, conservé) + V2 (retrieve_dense,
utilisé par les experts §5.2 — filtres section_type/doc_role/dossier_id)."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, IsNullCondition, MatchAny, MatchValue, PayloadField

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


async def retrieve_dense(
    query: str,
    *,
    tenant_id: UUID,
    top_k: int = 50,
    section_types: list[str] | None = None,
    doc_roles: list[str] | None = None,
    dossier_id: UUID | None = None,
) -> list[dict]:
    """V2 — utilisée par les experts (§5.2). HNSW (Qdrant) : approché, pas un
    scan exhaustif de la base (§4.2). `section_type` reste un filtre DOUX :
    `should` avec le NULL autorisé, jamais un `must` qui rendrait invisible
    un chunk non classé (§3.1, fail open)."""

    return await asyncio.to_thread(
        _retrieve_dense_sync,
        query,
        tenant_id=tenant_id,
        top_k=top_k,
        section_types=section_types,
        doc_roles=doc_roles,
        dossier_id=dossier_id,
    )


def _retrieve_dense_sync(
    query: str,
    *,
    tenant_id: UUID,
    top_k: int,
    section_types: list[str] | None,
    doc_roles: list[str] | None,
    dossier_id: UUID | None,
) -> list[dict]:
    s = get_settings()
    client = QdrantClient(url=s.qdrant_url)
    names = [c.name for c in client.get_collections().collections]
    if s.qdrant_collection not in names:
        return []
    vector = embed_texts([query[:8000]], quiet=True)[0]

    must = [FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant_id)))]
    if doc_roles:
        if dossier_id:
            # Annexe scopée à CE dossier (§1.5) OR les rôles demandés — ne
            # masque jamais le patrimoine général au profit d'une annexe.
            must.append(
                Filter(
                    should=[
                        FieldCondition(key="doc_role", match=MatchAny(any=doc_roles)),
                        Filter(
                            must=[
                                FieldCondition(key="doc_role", match=MatchValue(value="annexe")),
                                FieldCondition(key="dossier_id", match=MatchValue(value=str(dossier_id))),
                            ]
                        ),
                    ],
                    min_should=1,
                )
            )
        else:
            must.append(FieldCondition(key="doc_role", match=MatchAny(any=doc_roles)))
    else:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="doc_role", match=MatchAny(any=ALLOWED_ROLES)),
                    Filter(
                        must=[
                            FieldCondition(key="doc_role", match=MatchValue(value="annexe")),
                            FieldCondition(
                                key="dossier_id",
                                match=MatchValue(value=str(dossier_id)) if dossier_id else MatchValue(value="__none__"),
                            ),
                        ]
                    ),
                ],
                min_should=1,
            )
        )

    if section_types:
        must.append(
            Filter(
                should=[
                    FieldCondition(key="section_type", match=MatchAny(any=section_types)),
                    IsNullCondition(is_null=PayloadField(key="section_type")),
                ],
                min_should=1,
            )
        )

    response = client.query_points(
        collection_name=s.qdrant_collection,
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
                "section_type": payload.get("section_type"),
                "text": payload.get("text") or "",
            }
        )
    return out

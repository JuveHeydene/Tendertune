"""Nœud retrieve : Qdrant dense. Ne rédige rien."""

from __future__ import annotations

from uuid import UUID

from app.rag.hybrid_retriever import retrieve_hybrid


def retrieve(state: dict) -> dict:
    tenant = state.get("tenant_id")
    query = state.get("query") or ""
    if not tenant or not query.strip():
        return {**state, "retrieved": []}
    hits = retrieve_hybrid(query, tenant_id=UUID(str(tenant)), top_k=8)
    return {**state, "retrieved": hits}

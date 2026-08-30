"""Recherche sparse (BM25-like) via Postgres full-text search — §4.3.

Réutilise `chunks.text_fts` (tsvector généré, config française) plutôt que
d'ajouter un moteur de recherche dédié — proportionné à l'échelle d'une PME
BTP, pas du web-scale (décision actée dans architecture_agentique_
retrieval_generation.md §7, point #4).

`websearch_to_tsquery` (pas `plainto_tsquery`) : tolère une requête en
langage naturel sans lever d'erreur sur la ponctuation, et supporte les
guillemets/exclusions si un utilisateur les tape.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession


async def retrieve_sparse(
    session: AsyncSession,
    query: str,
    *,
    tenant_id: UUID,
    top_k: int = 50,
    section_types: list[str] | None = None,
    doc_roles: list[str] | None = None,
    dossier_id: UUID | None = None,
    document_id: UUID | None = None,
) -> list[dict]:
    """Retourne les enfants (chunks.parent_id IS NOT NULL) classés par
    pertinence lexicale. Même granularité que le dense (§4.4) — condition
    nécessaire pour que la fusion RRF ait un sens (clé commune : chunk_id)."""

    query = (query or "").strip()
    if not query or not tenant_id:
        return []

    clauses = [
        "c.text_fts @@ websearch_to_tsquery('french', :query)",
        "d.tenant_id = :tenant_id",
        "c.parent_id IS NOT NULL",
    ]
    params: dict = {"query": query, "tenant_id": str(tenant_id), "top_k": top_k}

    if section_types:
        clauses.append("(c.section_type = ANY(:section_types) OR c.section_type IS NULL)")
        params["section_types"] = section_types
    if doc_roles:
        clauses.append("d.doc_role = ANY(:doc_roles)")
        params["doc_roles"] = doc_roles
    if dossier_id:
        # Annexe scopée à CE dossier uniquement (§1.5) — OR avec les
        # doc_roles normaux pour ne jamais masquer le patrimoine général.
        clauses.append("(d.dossier_id = :dossier_id OR d.doc_role != 'annexe')")
        params["dossier_id"] = str(dossier_id)
    else:
        clauses.append("d.doc_role != 'annexe'")
    if document_id:
        clauses.append("c.document_id = :document_id")
        params["document_id"] = str(document_id)

    sql = f"""
        SELECT c.id AS chunk_id, c.document_id, c.page, c.heading_path,
               c.parent_id, d.doc_role,
               left(c.text, 2000) AS text,
               ts_rank_cd(c.text_fts, websearch_to_tsquery('french', :query)) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(clauses)}
        ORDER BY score DESC
        LIMIT :top_k
    """
    rows = (await session.execute(sql_text(sql), params)).mappings().all()
    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "document_id": str(row["document_id"]),
            "page": row["page"],
            "heading_path": row["heading_path"],
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "doc_role": row["doc_role"],
            "text": row["text"] or "",
            "score": float(row["score"] or 0),
        }
        for row in rows
    ]

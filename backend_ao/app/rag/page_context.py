"""Expansion RAG : tous les parents d'un même bloc/page logique."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.models.sql import ChunkRow
from app.services.db_client import session_factory

log = logging.getLogger("btp.rag")


def expand_hits_with_page_parents(hits: list[dict]) -> list[dict]:
    if not hits:
        return hits
    try:
        return asyncio.run(_expand_hits_async(hits))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_expand_hits_async(hits))
        finally:
            loop.close()


async def _expand_hits_async(hits: list[dict]) -> list[dict]:
    keys = _expansion_keys(hits)
    if not keys:
        return hits

    factory = session_factory()
    async with factory() as session:
        parents_by_key = await _load_parents(session, keys)

    expanded: list[dict] = []
    for hit in hits:
        key = _hit_key(hit)
        parents = parents_by_key.get(key) if key else None
        if not parents:
            expanded.append(hit)
            continue
        page_text = "\n\n".join(p.text for p in parents if p.text)
        expanded.append(
            {
                **hit,
                "match_text": hit.get("text") or "",
                "text": page_text,
                "page_parent_count": len(parents),
                "page_group": hit.get("page_group"),
            }
        )
    log.info(
        "RAG page context : %s hits, %s clés parent, %s enrichis",
        len(hits),
        len(keys),
        sum(1 for h in expanded if h.get("page_parent_count")),
    )
    return expanded


def _expansion_keys(hits: list[dict]) -> set[tuple[UUID, str]]:
    keys: set[tuple[UUID, str]] = set()
    for hit in hits:
        key = _hit_key(hit)
        if key:
            keys.add(key)
    return keys


def _hit_key(hit: dict) -> tuple[UUID, str] | None:
    doc_raw = hit.get("document_id")
    if not doc_raw:
        return None
    try:
        doc_id = UUID(str(doc_raw))
    except ValueError:
        return None
    page_group = hit.get("page_group")
    if page_group:
        return doc_id, f"g:{page_group}"
    page = hit.get("page")
    if page is None:
        return None
    return doc_id, f"p:{page}"


async def _load_parents(
    session,
    keys: set[tuple[UUID, str]],
) -> dict[tuple[UUID, str], list[ChunkRow]]:
    doc_ids = {doc_id for doc_id, _ in keys}
    group_keys = {key for key in keys if key[1].startswith("g:")}
    page_keys = {key for key in keys if key[1].startswith("p:")}

    out: dict[tuple[UUID, str], list[ChunkRow]] = {}

    if group_keys:
        groups = {key[1][2:] for key in group_keys}
        rows = (
            await session.execute(
                select(ChunkRow).where(
                    ChunkRow.document_id.in_(doc_ids),
                    ChunkRow.parent_id.is_(None),
                    ChunkRow.extra["page_group"].as_string().in_(groups),
                )
            )
        ).scalars().all()
        for row in rows:
            group = (row.extra or {}).get("page_group")
            if not group:
                continue
            key = (row.document_id, f"g:{group}")
            if key not in group_keys:
                continue
            out.setdefault(key, []).append(row)

    if page_keys:
        pages = {int(key[1][2:]) for key in page_keys}
        rows = (
            await session.execute(
                select(ChunkRow).where(
                    ChunkRow.document_id.in_(doc_ids),
                    ChunkRow.parent_id.is_(None),
                    ChunkRow.page.in_(pages),
                )
            )
        ).scalars().all()
        for row in rows:
            if row.page is None:
                continue
            key = (row.document_id, f"p:{row.page}")
            if key not in page_keys:
                continue
            out.setdefault(key, []).append(row)

    for key, items in out.items():
        items.sort(
            key=lambda r: (
                int((r.extra or {}).get("parent_index", 0)),
                r.created_at,
            )
        )
    return out

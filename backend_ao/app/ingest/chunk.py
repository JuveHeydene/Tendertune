"""Découpe parent (section) / enfant (fenêtre de texte)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.ingest.parse import ParsedDocument, ParsedPage

CHILD_SIZE = 1100
CHILD_OVERLAP = 120
PARENT_SIZE = 8000


@dataclass
class ChunkDraft:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    text: str
    heading_path: str | None
    page: int | None
    token_count: int
    extra: dict


def chunk_document(parsed: ParsedDocument) -> list[ChunkDraft]:
    out: list[ChunkDraft] = []
    for block in parsed.pages:
        out.extend(_chunk_block(block))
    if not out and parsed.pages:
        # Des pages existaient mais aucune n'a produit de texte exploitable :
        # signal d'échec réel (parse cassé), pas un actif visuel volontaire.
        raise ValueError("Aucun chunk produit")
    # parsed.pages == [] (ex. image sans texte OCR, cf. parse._parse_image) :
    # 0 chunk est le comportement ATTENDU, pas une erreur — le document reste
    # "ready" en tant qu'actif visuel (Nouvelle_Architecture/
    # base_de_donnees_et_interface.md §5.2).
    return out


def _parent_segments(text: str) -> list[str]:
    if len(text) <= PARENT_SIZE:
        return [text]
    segments: list[str] = []
    start = 0
    while start < len(text):
        segments.append(text[start : start + PARENT_SIZE])
        start += PARENT_SIZE
    return segments


def _chunk_block(block: ParsedPage) -> list[ChunkDraft]:
    text = (block.text or "").strip()
    if not text:
        return []
    page_group = str(uuid.uuid4())
    segments = _parent_segments(text)
    n_parents = len(segments)
    out: list[ChunkDraft] = []

    for idx, segment in enumerate(segments):
        parent_id = uuid.uuid4()
        parent_extra = {
            "kind": "parent",
            "page_group": page_group,
            "parent_index": idx,
            "parent_total": n_parents,
        }
        parent = ChunkDraft(
            id=parent_id,
            parent_id=None,
            text=segment,
            heading_path=block.heading_path,
            page=block.page,
            token_count=max(1, len(segment) // 4),
            extra=parent_extra,
        )
        pieces = _windows(segment)
        if n_parents == 1 and len(pieces) == 1 and len(segment) <= CHILD_SIZE:
            return [parent]

        out.append(parent)
        if len(pieces) == 1 and len(segment) <= CHILD_SIZE:
            continue
        for piece in pieces:
            out.append(
                ChunkDraft(
                    id=uuid.uuid4(),
                    parent_id=parent_id,
                    text=piece,
                    heading_path=block.heading_path,
                    page=block.page,
                    token_count=max(1, len(piece) // 4),
                    extra={
                        "kind": "child",
                        "page_group": page_group,
                        "parent_index": idx,
                        "parent_total": n_parents,
                    },
                )
            )
    return out


def _windows(text: str) -> list[str]:
    if len(text) <= CHILD_SIZE:
        return [text]
    parts = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHILD_SIZE)
        parts.append(text[start:end])
        if end == len(text):
            break
        start = end - CHILD_OVERLAP
    return parts

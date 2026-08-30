"""Tests chunking parent/enfant."""

from __future__ import annotations

from app.ingest.chunk import CHILD_SIZE, PARENT_SIZE, chunk_document
from app.ingest.parse import ParsedDocument, ParsedPage


def test_short_block_single_parent_no_children():
    text = "a" * 500
    parsed = ParsedDocument(pages=[ParsedPage(page=1, text=text)])
    drafts = chunk_document(parsed)
    assert len(drafts) == 1
    assert drafts[0].parent_id is None
    assert drafts[0].extra["kind"] == "parent"
    assert len(drafts[0].text) == 500


def test_long_block_multiple_parents_and_children():
    text = "x" * 10_000
    parsed = ParsedDocument(pages=[ParsedPage(page=3, text=text, heading_path="Lot A")])
    drafts = chunk_document(parsed)

    parents = [d for d in drafts if d.parent_id is None]
    children = [d for d in drafts if d.parent_id is not None]

    assert len(parents) == 2
    assert len(parents[0].text) == PARENT_SIZE
    assert len(parents[1].text) == 10_000 - PARENT_SIZE
    assert parents[0].extra["parent_index"] == 0
    assert parents[1].extra["parent_index"] == 1
    assert parents[0].extra["page_group"] == parents[1].extra["page_group"]
    assert all(c.extra["page_group"] == parents[0].extra["page_group"] for c in children)

    parent1_child_text = "".join(c.text for c in children if c.parent_id == parents[0].id)
    assert len(parent1_child_text) >= PARENT_SIZE - CHILD_SIZE
    parent2_children = [c for c in children if c.parent_id == parents[1].id]
    assert parent2_children
    assert sum(len(c.text) for c in parent2_children) >= 10_000 - PARENT_SIZE - CHILD_SIZE


def test_empty_pages_returns_empty_list_no_raise():
    """V2 — image sans texte OCR exploitable (actif visuel, §5.2) :
    0 chunk est le comportement ATTENDU, pas une erreur."""
    parsed = ParsedDocument(pages=[], parser="image-actif-visuel", page_count=0)
    assert chunk_document(parsed) == []


def test_blank_pages_present_still_raises():
    """Si des pages existaient mais sont vides après strip, c'est un échec
    réel de parse (document cassé), pas un actif visuel volontaire."""
    import pytest

    parsed = ParsedDocument(pages=[ParsedPage(page=1, text="   ")])
    with pytest.raises(ValueError):
        chunk_document(parsed)


def test_medium_block_one_parent_many_children():
    text = "b" * 5000
    parsed = ParsedDocument(pages=[ParsedPage(page=2, text=text)])
    drafts = chunk_document(parsed)
    parents = [d for d in drafts if d.parent_id is None]
    children = [d for d in drafts if d.parent_id is not None]
    assert len(parents) == 1
    assert len(parents[0].text) == 5000
    assert len(children) >= 4

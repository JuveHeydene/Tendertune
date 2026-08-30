"""Tests matching flou d’entités graphe."""

from __future__ import annotations

from app.graph.entity_match import EntityMatchIndex, resolve_entity_key


def _index_with(*pairs: tuple[str, str]) -> EntityMatchIndex:
    idx = EntityMatchIndex(use_embeddings=False)
    for name, key in pairs:
        idx.add(name, key)
    return idx


def test_exact_match():
    idx = _index_with(("BTP Construction", "t:ENTREPRISE:btp construction"))
    hit = idx.resolve("BTP Construction")
    assert hit is not None
    assert hit.method == "exact"
    assert hit.key.endswith("btp construction")


def test_levenshtein_plural():
    idx = _index_with(("BTP Construction", "t:ENTREPRISE:btp construction"))
    hit = idx.resolve("BTP Constructions")
    assert hit is not None
    assert hit.method == "levenshtein"
    assert hit.score >= 85
    assert hit.key == "t:ENTREPRISE:btp construction"


def test_token_set_word_order():
    idx = _index_with(("Jean Dupont", "t:PERSONNE:jean dupont"))
    hit = idx.resolve("Dupont Jean")
    assert hit is not None
    assert hit.method in ("exact", "levenshtein", "jaccard_token_set")
    assert hit.key == "t:PERSONNE:jean dupont"


def test_no_match_far_apart():
    idx = _index_with(("Tour Eiffel", "t:PROJET:tour eiffel"))
    assert idx.resolve("Certification ISO 9001") is None


def test_resolve_helper():
    idx = _index_with(("Lot 3 VRD", "t:LOT:lot 3 vrd"))
    assert resolve_entity_key(idx, "Lot 3 VRD") == "t:LOT:lot 3 vrd"
    assert resolve_entity_key(idx, "Société Inconnue XYZ") is None

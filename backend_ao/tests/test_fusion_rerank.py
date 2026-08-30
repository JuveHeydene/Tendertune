"""Tests RRF fusion et rerank lexical — purs, déterministes, sans réseau."""

from __future__ import annotations

from app.rag.fusion import rrf_fuse
from app.rag.rerank import rerank


def test_rrf_favors_item_ranked_first_in_either_list():
    dense = [{"chunk_id": "d1", "text": "a"}, {"chunk_id": "d5", "text": "b"}]
    sparse = [{"chunk_id": "d8", "text": "c"}, {"chunk_id": "d1", "text": "a"}]
    fused = rrf_fuse(dense, sparse)
    ids = [f["chunk_id"] for f in fused]
    # d1 est 1er dense ET 2e sparse -> doit dominer un item présent une seule fois
    assert ids[0] == "d1"


def test_rrf_deduplicates_by_chunk_id():
    dense = [{"chunk_id": "x", "text": "a"}]
    sparse = [{"chunk_id": "x", "text": "a"}]
    fused = rrf_fuse(dense, sparse)
    assert len(fused) == 1


def test_rrf_empty_lists():
    assert rrf_fuse([], []) == []


def test_rerank_prefers_lexical_overlap_over_pure_rrf_position():
    query = "pénalité de retard contrat Dupont"
    nodes = [
        {"chunk_id": "a", "text": "Durée standard du marché 12 mois.", "rrf_score": 0.05},
        {
            "chunk_id": "b",
            "text": "Clause de pénalité de retard applicable au contrat Dupont.",
            "rrf_score": 0.01,
        },
    ]
    ranked = rerank(query, nodes, top_n=2)
    assert ranked[0]["chunk_id"] == "b"


def test_rerank_respects_top_n():
    nodes = [{"chunk_id": str(i), "text": "texte", "rrf_score": 0.01 * i} for i in range(20)]
    ranked = rerank("texte", nodes, top_n=5)
    assert len(ranked) == 5


def test_rerank_empty_input():
    assert rerank("query", [], top_n=8) == []

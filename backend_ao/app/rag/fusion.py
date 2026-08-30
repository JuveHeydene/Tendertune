"""Reciprocal Rank Fusion — §4.4. Fusionne des CLASSEMENTS (rangs), pas des
scores incomparables (cosine dense vs ts_rank_cd sparse n'ont pas la même
échelle). Même clé (chunk_id) des deux côtés, même granularité (enfants)."""

from __future__ import annotations

RRF_K = 60


def rrf_fuse(*ranked_lists: list[dict], k: int = RRF_K) -> list[dict]:
    """Chaque liste est déjà triée par pertinence décroissante. Retourne une
    liste unique triée par score RRF décroissant, dédupliquée par chunk_id,
    en conservant le meilleur enregistrement (le plus riche en métadonnées)
    rencontré pour chaque chunk."""

    scores: dict[str, float] = {}
    best_record: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            chunk_id = item.get("chunk_id")
            if not chunk_id:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk_id not in best_record:
                best_record[chunk_id] = item

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for chunk_id, rrf_score in ordered:
        record = dict(best_record[chunk_id])
        record["rrf_score"] = rrf_score
        out.append(record)
    return out

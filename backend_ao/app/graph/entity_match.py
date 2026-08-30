"""Matching flou d’entités pour relations Neo4j (exact → Levenshtein → Jaccard → embed)."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

log = logging.getLogger("btp.graph.match")

LEV_THRESHOLD = 85
TOKEN_THRESHOLD = 80
EMBED_THRESHOLD = 0.82


def norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


@dataclass
class MatchResult:
    key: str
    method: str
    score: float


@dataclass
class EntityMatchIndex:
    """Index nom → clé Neo4j, avec recherche exacte puis fuzzy."""

    # formes normalisées et brutes → clé
    name_to_key: dict[str, str] = field(default_factory=dict)
    # une entrée par entité unique (nom d’affichage pour fuzzy / embed)
    candidates: list[tuple[str, str]] = field(default_factory=list)  # (norm_name, key)
    _embed_cache: dict[str, list[float]] = field(default_factory=dict, repr=False)
    use_embeddings: bool = True

    def add(self, name: str, key: str) -> None:
        raw = name.strip()
        n = norm_name(raw)
        if not n:
            return
        self.name_to_key[raw] = key
        self.name_to_key[n] = key
        if not any(c[1] == key for c in self.candidates):
            self.candidates.append((n, key))

    def resolve(self, name: str) -> MatchResult | None:
        raw = str(name or "").strip()
        if not raw:
            return None
        n = norm_name(raw)

        if raw in self.name_to_key:
            return MatchResult(self.name_to_key[raw], "exact", 100.0)
        if n in self.name_to_key:
            return MatchResult(self.name_to_key[n], "exact", 100.0)

        lev = self._best_levenshtein(n)
        if lev is not None:
            return lev

        tok = self._best_token_set(n)
        if tok is not None:
            return tok

        if self.use_embeddings and self.candidates:
            emb = self._best_embedding(raw)
            if emb is not None:
                return emb

        return None

    def _best_levenshtein(self, name_norm: str) -> MatchResult | None:
        try:
            from rapidfuzz import fuzz
        except ImportError:
            log.warning("rapidfuzz absent — fuzzy Levenshtein désactivé")
            return None
        best_score = 0.0
        best_key: str | None = None
        for cand_name, key in self.candidates:
            score = float(fuzz.ratio(name_norm, cand_name))
            if score > best_score and score >= LEV_THRESHOLD:
                best_score = score
                best_key = key
        if best_key is None:
            return None
        return MatchResult(best_key, "levenshtein", best_score)

    def _best_token_set(self, name_norm: str) -> MatchResult | None:
        try:
            from rapidfuzz import fuzz
        except ImportError:
            return None
        best_score = 0.0
        best_key: str | None = None
        for cand_name, key in self.candidates:
            score = float(fuzz.token_set_ratio(name_norm, cand_name))
            if score > best_score and score >= TOKEN_THRESHOLD:
                best_score = score
                best_key = key
        if best_key is None:
            return None
        return MatchResult(best_key, "jaccard_token_set", best_score)

    def _best_embedding(self, name: str) -> MatchResult | None:
        try:
            from app.ingest.index_qdrant import embed_texts
        except Exception as exc:
            log.warning("embeddings indisponibles pour fuzzy : %s", exc)
            return None
        if not self.candidates:
            return None
        try:
            query_vec = embed_texts([name[:500]], quiet=True)[0]
            missing = [c[0] for c in self.candidates if c[0] not in self._embed_cache]
            if missing:
                vectors = embed_texts([m[:500] for m in missing], quiet=True)
                for label, vec in zip(missing, vectors, strict=True):
                    self._embed_cache[label] = vec
        except Exception as exc:
            log.warning("fuzzy embed échec (%s) — skip sémantique", exc)
            return None

        best_score = 0.0
        best_key: str | None = None
        for cand_name, key in self.candidates:
            cand_vec = self._embed_cache.get(cand_name)
            if not cand_vec:
                continue
            score = _cosine(query_vec, cand_vec)
            if score > best_score and score >= EMBED_THRESHOLD:
                best_score = score
                best_key = key
        if best_key is None:
            return None
        return MatchResult(best_key, "embedding", best_score)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def resolve_entity_key(index: EntityMatchIndex, name: str) -> str | None:
    hit = index.resolve(name)
    if hit is None:
        log.debug("fuzzy : aucun match pour %r", name)
        return None
    if hit.method != "exact":
        log.info(
            "fuzzy match %s score=%.1f  %r → key=%s",
            hit.method,
            hit.score,
            name,
            hit.key,
        )
    return hit.key

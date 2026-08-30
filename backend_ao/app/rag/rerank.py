"""Rerank BGE — CPU par défaut, GPU seulement si USE_GPU=true."""

from app.config import get_settings


def rerank(query: str, nodes: list, top_n: int = 8) -> list:
    s = get_settings()
    _ = (query, s.rerank_model, s.device, top_n)
    # Plus tard : FlagEmbeddingReranker, model.to(s.device)
    return nodes[:top_n]

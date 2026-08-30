"""Factory LlamaIndex branchée sur Ollama (LLM + embeddings) et Qdrant."""

from llama_index.core import Settings as LlamaSettings
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import get_settings


def configure_llama_index() -> None:
    """À appeler une fois au démarrage du worker / de l'API."""
    s = get_settings()
    if s.embed_provider != "ollama" or s.llm_provider != "ollama":
        raise RuntimeError(
            "V1 locale : seuls LLM_PROVIDER=ollama et EMBED_PROVIDER=ollama sont branchés. "
            "HuggingFace / API viendront ensuite."
        )

    LlamaSettings.embed_model = OllamaEmbedding(
        model_name=s.embed_model,
        base_url=s.ollama_base_url,
    )
    LlamaSettings.llm = Ollama(
        model=s.llm_model,
        base_url=s.ollama_base_url,
        request_timeout=120.0,
    )


def get_qdrant_client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(url=s.qdrant_url)


def get_vector_index() -> VectorStoreIndex:
    s = get_settings()
    store = QdrantVectorStore(
        client=get_qdrant_client(),
        collection_name=s.qdrant_collection,
        enable_hybrid=False,
    )
    return VectorStoreIndex.from_vector_store(store)

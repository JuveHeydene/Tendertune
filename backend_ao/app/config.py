"""Configuration centralisée — une seule source de vérité : le fichier .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Interrupteur GPU : tout le reste (Paddle, Docker overlay) s'aligne dessus.
    use_gpu: bool = False

    # PostgreSQL
    database_url: str = "postgresql://ao_user:ao_pass@localhost:5432/ao_db"
    postgres_user: str = "ao_user"
    postgres_password: str = "ao_pass"
    postgres_db: str = "ao_db"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_grpc_host: str = "localhost"
    qdrant_grpc_port: int = 6334
    qdrant_collection: str = "ao_chunks"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password123"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_raw: str = "ao-raw"
    minio_bucket_export: str = "ao-exports"
    minio_use_ssl: bool = False

    # LLM / embeddings — Ollama en local par défaut
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3"
    embed_provider: str = "ollama"
    embed_model: str = "nomic-embed-text"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "info"
    jwt_secret: str = "change-me-btp-rag-dev"
    jwt_expire_minutes: int = 60
    admin_email: str = "admin@btp.local"
    admin_username: str = "admin"
    admin_password: str = "AdminChantier2026!"
    admin_first_name: str = "Admin"
    admin_last_name: str = "Plateforme"

    @property
    def device(self) -> str:
        """Cible PyTorch / Paddle : 'cuda' seulement si USE_GPU=true."""
        return "cuda" if self.use_gpu else "cpu"


@lru_cache
def get_settings() -> Settings:
    return Settings()

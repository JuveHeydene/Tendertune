"""Client SQLAlchemy async — Postgres via asyncpg uniquement (pas de psycopg)."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.sql import Base

_engine = None
_SessionLocal = None


def _asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = _asyncpg_url(get_settings().database_url)
        _engine = create_async_engine(url, pool_pre_ping=True)
        _SessionLocal = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _engine


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = session_factory()
    async with factory() as session:
        yield session


def session_factory():
    get_engine()
    return _SessionLocal


async def create_tables() -> None:
    """Utile en dev si l'init SQL Docker n'a pas tourné. En prod : scripts/init_db.sql."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

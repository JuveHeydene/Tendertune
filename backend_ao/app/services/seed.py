"""Bootstrap idempotent : tenant `default` + un admin, puis suppression des comptes démo.

Le SQL d'init (volume Postgres vide) ne peut pas hasher bcrypt de façon fiable
alignée sur Python. Ce module tourne à chaque démarrage API, ne crée l'admin
que s'il n'existe pas encore, et retire les emails *@demo.local.
"""

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Tenant, User
from app.services.security import hash_password


async def bootstrap_platform(session: AsyncSession) -> None:
    await session.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS ingest_error TEXT"))
    await session.commit()
    settings = get_settings()
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == "default"))
    ).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(
            slug="default",
            name="Chantier Offres",
            email=settings.admin_email.lower(),
            status="active",
        )
        session.add(tenant)
        await session.flush()
    elif tenant.name == "Entreprise Demo" or tenant.email.endswith("@demo.local"):
        tenant.name = "Chantier Offres"
        tenant.email = settings.admin_email.lower()

    await session.execute(delete(User).where(User.email.ilike("%@demo.local")))

    existing = (
        await session.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == settings.admin_email.lower(),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        if not settings.admin_password:
            raise RuntimeError("ADMIN_PASSWORD vide : impossible de créer l’admin")
        session.add(
            User(
                tenant_id=tenant.id,
                username=settings.admin_username,
                email=settings.admin_email.lower(),
                hashed_password=hash_password(settings.admin_password),
                first_name=settings.admin_first_name,
                last_name=settings.admin_last_name,
                role="admin",
                status="active",
            )
        )
    await session.commit()

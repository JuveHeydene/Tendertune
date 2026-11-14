"""Auth JWT — login, moi, logout (révocation session)."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Session as DbSession
from app.models.sql import Tenant, User
from app.services.audit import record_audit
from app.services.db_client import get_session
from app.services.security import create_access_token, decode_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

ROLES = ("admin", "manager", "redacteur", "consultant")


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)


class UserPublic(BaseModel):
    id: UUID
    email: str
    username: str
    first_name: str | None
    last_name: str | None
    role: str
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


def _token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Jeton invalide")

    stored = (
        await session.execute(
            select(DbSession).where(
                DbSession.token_hash == _token_hash(token),
                DbSession.revoked.is_(False),
            )
        )
    ).scalar_one_or_none()
    if stored is None or stored.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    user = await session.get(User, user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Compte inactif")
    stored.last_activity_at = datetime.now(UTC)
    await session.commit()
    return user


def require_roles(*roles: str):
    async def _inner(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Droits insuffisants")
        return user

    return _inner


def _public(user: User, tenant: Tenant) -> UserPublic:
    return UserPublic(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
    )


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)):
    email = body.email.lower().strip()
    candidates = (
        await session.execute(select(User).where(User.email == email))
    ).scalars().all()
    if len(candidates) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plusieurs comptes portent cet email. Contactez l’administrateur.",
        )
    user = candidates[0] if candidates else None
    if user is None or not verify_password(body.password, user.hashed_password):
        if user is not None:
            user.login_attempts = (user.login_attempts or 0) + 1
            await record_audit(
                session, tenant_id=user.tenant_id, user_id=user.id, action_type="login",
                resource_type="user", resource_id=user.id, request=request,
                success=False, error_message="Mot de passe incorrect",
            )
            await session.commit()
        # user is None (email inconnu) : aucun tenant à qui rattacher une
        # ligne d'audit — rien de exploitable à journaliser dans ce schéma
        # scopé par tenant.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiants incorrects")
    if user.status != "active":
        await record_audit(
            session, tenant_id=user.tenant_id, user_id=user.id, action_type="login",
            resource_type="user", resource_id=user.id, request=request,
            success=False, error_message="Compte suspendu",
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte suspendu")

    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "active":
        await record_audit(
            session, tenant_id=user.tenant_id, user_id=user.id, action_type="login",
            resource_type="user", resource_id=user.id, request=request,
            success=False, error_message="Entreprise suspendue",
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Entreprise suspendue")

    user.login_attempts = 0
    user.last_login_at = datetime.now(UTC)
    token = create_access_token(
        user_id=user.id, tenant_id=tenant.id, role=user.role, email=user.email
    )
    expires = datetime.now(UTC) + timedelta(minutes=get_settings().jwt_expire_minutes)
    session.add(
        DbSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            ip_address=request.client.host if request.client else None,
            expires_at=expires,
        )
    )
    await record_audit(
        session, tenant_id=tenant.id, user_id=user.id, action_type="login",
        resource_type="user", resource_id=user.id, request=request, success=True,
    )
    await session.commit()
    return LoginResponse(access_token=token, user=_public(user, tenant))


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    tenant = await session.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant introuvable")
    return _public(user, tenant)


@router.post("/logout")
async def logout(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
):
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        row = (
            await session.execute(select(DbSession).where(DbSession.token_hash == _token_hash(token)))
        ).scalar_one_or_none()
        if row is not None:
            row.revoked = True
            row.revoked_at = datetime.now(UTC)
            owner = await session.get(User, row.user_id)
            if owner is not None:
                await record_audit(
                    session, tenant_id=owner.tenant_id, user_id=owner.id, action_type="logout",
                    resource_type="user", resource_id=owner.id, request=request, success=True,
                )
            await session.commit()
    return {"ok": True}

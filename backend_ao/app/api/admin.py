"""Administration plateforme : tenants, utilisateurs, sessions."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import UserPublic, require_roles
from app.models.sql import AuditLog
from app.models.sql import Session as DbSession
from app.models.sql import Tenant, User
from app.services.audit import record_audit
from app.services.db_client import get_session
from app.services.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])
ROLES = ("admin", "manager", "redacteur", "consultant")
AdminUser = require_roles("admin")


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    email: str
    status: str


class TenantCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    email: str
    status: str = "active"


class TenantPatch(BaseModel):
    name: str | None = None
    email: str | None = None
    status: str | None = None


class UserOut(UserPublic):
    status: str
    last_login_at: datetime | None


class UserCreate(BaseModel):
    tenant_id: UUID
    username: str = Field(min_length=2, max_length=64)
    email: str
    password: str = Field(min_length=8)
    role: str
    first_name: str | None = None
    last_name: str | None = None


class UserPatch(BaseModel):
    role: str | None = None
    status: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    password: str | None = Field(default=None, min_length=8)


class SessionOut(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    username: str
    user_agent: str | None
    expires_at: datetime
    last_activity_at: datetime
    revoked: bool
    created_at: datetime


def _user_out(user: User, tenant: Tenant) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_slug=tenant.slug,
        tenant_name=tenant.name,
        status=user.status,
        last_login_at=user.last_login_at,
    )


@router.get("/tenants", response_model=list[TenantOut])
async def list_tenants(_: User = Depends(AdminUser), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Tenant).order_by(Tenant.slug))).scalars().all()
    return [TenantOut.model_validate(t, from_attributes=True) for t in rows]


@router.post("/tenants", response_model=TenantOut)
async def create_tenant(
    body: TenantCreate,
    request: Request,
    actor: User = Depends(AdminUser),
    session: AsyncSession = Depends(get_session),
):
    slug = body.slug.strip().lower()
    exists = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="Slug déjà utilisé")
    if body.status not in ("active", "suspended"):
        raise HTTPException(status_code=400, detail="Statut tenant invalide")
    tenant = Tenant(slug=slug, name=body.name.strip(), email=body.email.lower(), status=body.status)
    session.add(tenant)
    await session.flush()
    await record_audit(
        session, tenant_id=tenant.id, user_id=actor.id, action_type="create",
        resource_type="tenant", resource_id=tenant.id,
        details={"slug": tenant.slug, "name": tenant.name}, request=request,
    )
    await session.commit()
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant, from_attributes=True)


@router.patch("/tenants/{tenant_id}", response_model=TenantOut)
async def patch_tenant(
    tenant_id: UUID,
    body: TenantPatch,
    request: Request,
    actor: User = Depends(AdminUser),
    session: AsyncSession = Depends(get_session),
):
    tenant = await session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant introuvable")
    changes: dict = {}
    if body.status is not None:
        if body.status not in ("active", "suspended"):
            raise HTTPException(status_code=400, detail="Statut tenant invalide")
        if body.status != tenant.status:
            changes["status"] = {"from": tenant.status, "to": body.status}
        tenant.status = body.status
    if body.name:
        tenant.name = body.name.strip()
    if body.email:
        tenant.email = body.email.lower()
    if changes:
        # Seul le changement de statut (suspension/réactivation d'une
        # entreprise entière) est assez sensible pour justifier une trace —
        # renommer/changer l'email de contact ne l'est pas.
        await record_audit(
            session, tenant_id=tenant.id, user_id=actor.id, action_type="update",
            resource_type="tenant", resource_id=tenant.id, details={"changes": changes}, request=request,
        )
    await session.commit()
    await session.refresh(tenant)
    return TenantOut.model_validate(tenant, from_attributes=True)


@router.get("/users", response_model=list[UserOut])
async def list_users(_: User = Depends(AdminUser), session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(User).order_by(User.email))).scalars().all()
    tenants = {
        t.id: t
        for t in (await session.execute(select(Tenant))).scalars().all()
    }
    return [_user_out(u, tenants[u.tenant_id]) for u in rows if u.tenant_id in tenants]


@router.post("/users", response_model=UserOut)
async def create_user(
    body: UserCreate,
    request: Request,
    actor: User = Depends(AdminUser),
    session: AsyncSession = Depends(get_session),
):
    if body.role not in ROLES:
        raise HTTPException(status_code=400, detail="Rôle invalide")
    tenant = await session.get(Tenant, body.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant introuvable")
    email = body.email.lower().strip()
    clash = (
        await session.execute(select(User).where(User.tenant_id == tenant.id, User.email == email))
    ).scalar_one_or_none()
    if clash:
        raise HTTPException(status_code=409, detail="Email déjà utilisé sur ce tenant")
    user = User(
        tenant_id=tenant.id,
        username=body.username.strip(),
        email=email,
        hashed_password=hash_password(body.password),
        role=body.role,
        first_name=body.first_name,
        last_name=body.last_name,
        status="active",
    )
    session.add(user)
    await session.flush()
    await record_audit(
        session, tenant_id=tenant.id, user_id=actor.id, action_type="create",
        resource_type="user", resource_id=user.id,
        details={"email": user.email, "role": user.role}, request=request,
    )
    await session.commit()
    await session.refresh(user)
    return _user_out(user, tenant)


@router.patch("/users/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: UUID,
    body: UserPatch,
    request: Request,
    actor: User = Depends(AdminUser),
    session: AsyncSession = Depends(get_session),
):
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    changes: dict = {}
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(status_code=400, detail="Rôle invalide")
        if user.id == actor.id and body.role != "admin":
            raise HTTPException(status_code=400, detail="Impossible de retirer son propre rôle admin")
        if body.role != user.role:
            changes["role"] = {"from": user.role, "to": body.role}
        user.role = body.role
    if body.status is not None:
        if body.status not in ("active", "inactive", "suspended"):
            raise HTTPException(status_code=400, detail="Statut invalide")
        if user.id == actor.id and body.status != "active":
            raise HTTPException(status_code=400, detail="Impossible de se désactiver soi-même")
        if body.status != user.status:
            changes["status"] = {"from": user.status, "to": body.status}
        user.status = body.status
    if body.first_name is not None:
        user.first_name = body.first_name
    if body.last_name is not None:
        user.last_name = body.last_name
    if body.password:
        user.hashed_password = hash_password(body.password)
        changes["password_reset"] = True
    if changes:
        # Renommer un prénom n'a rien de sensible ; changer un rôle, un
        # statut ou réinitialiser un mot de passe, si — c'est exactement le
        # genre d'action qu'un audit doit pouvoir reconstituer après coup.
        await record_audit(
            session, tenant_id=user.tenant_id, user_id=actor.id, action_type="update",
            resource_type="user", resource_id=user.id, details={"changes": changes}, request=request,
        )
    await session.commit()
    tenant = await session.get(Tenant, user.tenant_id)
    return _user_out(user, tenant)


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(_: User = Depends(AdminUser), session: AsyncSession = Depends(get_session)):
    rows = (
        await session.execute(
            select(DbSession, User)
            .join(User, DbSession.user_id == User.id)
            .order_by(DbSession.created_at.desc())
        )
    ).all()
    return [
        SessionOut(
            id=s.id,
            user_id=s.user_id,
            email=u.email,
            username=u.username,
            user_agent=s.user_agent,
            expires_at=s.expires_at,
            last_activity_at=s.last_activity_at,
            revoked=s.revoked,
            created_at=s.created_at,
        )
        for s, u in rows
    ]


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(
    session_id: UUID,
    request: Request,
    actor: User = Depends(AdminUser),
    db: AsyncSession = Depends(get_session),
):
    row = await db.get(DbSession, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session introuvable")
    row.revoked = True
    row.revoked_at = datetime.now(UTC)
    target = await db.get(User, row.user_id)
    if target is not None:
        await record_audit(
            db, tenant_id=target.tenant_id, user_id=actor.id, action_type="revoke",
            resource_type="session", resource_id=session_id,
            details={"target_user_id": str(row.user_id)}, request=request,
        )
    await db.commit()
    return {"ok": True}


class AuditLogOut(BaseModel):
    id: UUID
    tenant_id: UUID
    user_id: UUID | None
    user_email: str | None
    action_type: str
    resource_type: str | None
    resource_id: UUID | None
    details: dict
    ip_address: str | None
    user_agent: str | None
    success: bool
    error_message: str | None
    created_at: datetime


@router.get("/audit-logs", response_model=list[AuditLogOut])
async def list_audit_logs(
    action_type: str | None = None,
    resource_type: str | None = None,
    tenant_id: UUID | None = None,
    success: bool | None = None,
    limit: int = 200,
    _: User = Depends(AdminUser),
    session: AsyncSession = Depends(get_session),
):
    """Consultation du journal d'audit (connexions, suppressions,
    changements de rôle/statut, révocations) — la table `audit_logs`
    existait dans le schéma depuis le début mais n'était jamais alimentée
    ni consultable avant ce endpoint."""
    limit = max(1, min(limit, 500))
    stmt = select(AuditLog, User.email).outerjoin(User, AuditLog.user_id == User.id)
    if action_type:
        stmt = stmt.where(AuditLog.action_type == action_type)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if success is not None:
        stmt = stmt.where(AuditLog.success == success)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [
        AuditLogOut(
            id=a.id, tenant_id=a.tenant_id, user_id=a.user_id, user_email=email,
            action_type=a.action_type, resource_type=a.resource_type, resource_id=a.resource_id,
            details=a.details or {}, ip_address=str(a.ip_address) if a.ip_address is not None else None,
            user_agent=a.user_agent, success=a.success, error_message=a.error_message,
            created_at=a.created_at,
        )
        for a, email in rows
    ]


@router.post("/users/{user_id}/revoke-sessions")
async def revoke_user_sessions(
    user_id: UUID,
    request: Request,
    actor: User = Depends(AdminUser),
    db: AsyncSession = Depends(get_session),
):
    rows = (await db.execute(select(DbSession).where(DbSession.user_id == user_id, DbSession.revoked.is_(False)))).scalars().all()
    now = datetime.now(UTC)
    for row in rows:
        row.revoked = True
        row.revoked_at = now
    target = await db.get(User, user_id)
    if target is not None and rows:
        await record_audit(
            db, tenant_id=target.tenant_id, user_id=actor.id, action_type="revoke",
            resource_type="session", resource_id=None,
            details={"target_user_id": str(user_id), "count": len(rows)}, request=request,
        )
    await db.commit()
    return {"ok": True, "revoked": len(rows)}

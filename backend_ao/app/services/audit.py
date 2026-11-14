"""Journal d'audit — actions sensibles (connexion, suppression, changement
de rôle/statut, révocation de session). La table `audit_logs` existait dans
le schéma depuis le début (id, tenant_id, user_id, action_type,
resource_type/resource_id, details JSONB, ip_address, user_agent, success,
error_message) mais n'était alimentée par AUCUN code — un audit trail
prévu mais jamais branché. Cette fonction est le seul point d'écriture,
appelé depuis les endpoints qui touchent à des ressources sensibles
(app/api/auth.py, app/api/admin.py, app/api/documents.py)."""

from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sql import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
    action_type: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict | None = None,
    request: Request | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """`flush`, pas `commit` — l'entrée d'audit rejoint la transaction en
    cours chez l'appelant, pour être annulée avec le reste si l'action
    échoue avant son propre commit (sauf quand l'appelant audite un échec
    après un rollback : dans ce cas c'est une écriture séparée, volontaire)."""
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action_type=action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=request.client.host if request and request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:512] if request else None,
            success=success,
            error_message=error_message[:2000] if error_message else None,
        )
    )
    await session.flush()

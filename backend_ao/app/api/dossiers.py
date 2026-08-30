"""Workflow dossier : listing, export multi-format."""

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.models.pydantic import ReviewAction
from app.models.sql import Dossier, Export, User
from app.services.db_client import get_session
from app.services.dossier_workflow import EXT, MIME
from app.services.minio_client import get_minio

router = APIRouter(prefix="/dossiers", tags=["dossiers"])

WRITE_ROLES = {"admin", "manager", "redacteur"}


class DossierOut(BaseModel):
    id: UUID
    client_name: str | None
    project_name: str | None
    dao_reference: str | None
    status: str
    deadline: str | None
    current_version: int | None = None


@router.get("", response_model=list[DossierOut])
async def list_dossiers(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Dossier)
            .where(Dossier.tenant_id == user.tenant_id)
            .order_by(Dossier.updated_at.desc())
        )
    ).scalars().all()
    return [
        DossierOut(
            id=d.id,
            client_name=d.client_name,
            project_name=d.project_name,
            dao_reference=d.dao_reference,
            status=d.status,
            deadline=d.deadline.isoformat() if d.deadline else None,
            current_version=d.current_version,
        )
        for d in rows
    ]


@router.post("/{dossier_id}/run")
async def run_dossier(dossier_id: str):
    return {
        "dossier_id": dossier_id,
        "status": "use_conversation",
        "hint": "Rédigez les sections dans Conversations puis exportez.",
    }


@router.post("/{dossier_id}/sections/{section_id}/review")
async def review_section(dossier_id: str, section_id: str, body: ReviewAction):
    return {
        "dossier_id": dossier_id,
        "section_id": section_id,
        "action": body.action,
        "status": "not_implemented",
    }


@router.get("/{dossier_id}/export.{fmt}")
async def download_export(
    dossier_id: UUID,
    fmt: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if fmt not in EXT:
        raise HTTPException(status_code=400, detail=f"Format {fmt!r} invalide")
    if user.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Export réservé au rédacteur, manager ou admin")
    doss = await session.get(Dossier, dossier_id)
    if doss is None or doss.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    rec = (
        await session.execute(
            select(Export)
            .where(Export.dossier_id == doss.id, Export.format == fmt)
            .order_by(Export.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail="Aucun export pour ce format. Utilisez Exporter le document en conversation.",
        )
    settings = get_settings()
    response = None
    try:
        response = get_minio().get_object(settings.minio_bucket_export, rec.object_key)
        data = response.read()
    finally:
        if response is not None:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass
    base = (doss.project_name or str(doss.id)).replace(" ", "_")
    filename = f"memoire-{base}-v{rec.version}.{EXT[fmt]}"
    return StreamingResponse(
        BytesIO(data),
        media_type=MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

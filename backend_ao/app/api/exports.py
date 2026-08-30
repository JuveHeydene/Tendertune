"""Listing et téléchargement des exports mémoire (MinIO ao-exports)."""

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import get_settings
from app.models.sql import Dossier, Export, User
from app.services.db_client import get_session
from app.services.dossier_workflow import EXT, MIME
from app.services.minio_client import get_minio

router = APIRouter(prefix="/exports", tags=["exports"])

WRITE_ROLES = {"admin", "manager", "redacteur"}


class ExportOut(BaseModel):
    id: UUID
    dossier_id: UUID
    project_name: str | None
    format: str
    version: int
    size_bytes: int | None
    created_at: str
    download_name: str


@router.get("", response_model=list[ExportOut])
async def list_exports(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Export, Dossier.project_name)
            .join(Dossier, Export.dossier_id == Dossier.id)
            .where(Dossier.tenant_id == user.tenant_id)
            .order_by(Export.created_at.desc())
        )
    ).all()
    out: list[ExportOut] = []
    for rec, project_name in rows:
        base = (project_name or str(rec.dossier_id)).replace(" ", "_")
        ext = EXT.get(rec.format, rec.format)
        out.append(
            ExportOut(
                id=rec.id,
                dossier_id=rec.dossier_id,
                project_name=project_name,
                format=rec.format,
                version=rec.version,
                size_bytes=rec.size_bytes,
                created_at=rec.created_at.isoformat(),
                download_name=f"memoire-{base}-v{rec.version}.{ext}",
            )
        )
    return out


@router.get("/{export_id}/download")
async def download_export_by_id(
    export_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role not in WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Export réservé au rédacteur, manager ou admin")
    row = (
        await session.execute(
            select(Export, Dossier)
            .join(Dossier, Export.dossier_id == Dossier.id)
            .where(Export.id == export_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Export introuvable")
    rec, doss = row
    if doss.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="Export introuvable")
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
    fmt = rec.format
    base = (doss.project_name or str(doss.id)).replace(" ", "_")
    filename = f"memoire-{base}-v{rec.version}.{EXT[fmt]}"
    return StreamingResponse(
        BytesIO(data),
        media_type=MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

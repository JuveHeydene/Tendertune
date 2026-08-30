"""Indicateurs métier pour les tableaux de bord (V1, chiffres réels si tables peuplées)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.models.sql import Document, Dossier, ExigenceRow, Export, User
from app.services.db_client import get_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class DashboardSummary(BaseModel):
    role: str
    dossiers: int
    dossiers_en_cours: int
    documents_patrimoine: int
    documents_dao: int
    exigences_a_couvrir: int
    exports_count: int = 0
    headline: str
    focus: list[str]


_HEADLINES = {
    "admin": "Pilotage de la plateforme d’appels d’offres",
    "manager": "Portefeuille de consultations et échéances",
    "redacteur": "Vos mémoires techniques et sections à rédiger",
    "consultant": "Revue et lecture des dossiers en cours",
}

_FOCUS = {
    "admin": [
        "Utilisateurs et rôles du tenant",
        "Patrimoine documentaire et jobs d’ingestion",
        "Audit des exports et accès",
    ],
    "manager": [
        "Pipeline des AO (brouillon → export)",
        "Échéances de remise des offres",
        "Répartition de la charge rédaction",
    ],
    "redacteur": [
        "Générer une section à partir du patrimoine",
        "Couvrir les exigences du DAO courant",
        "Soumettre à revue humaine",
    ],
    "consultant": [
        "Consulter les versions de sections",
        "Valider ou commenter (HITL)",
        "Pas d’export sans rôle manager / admin",
    ],
}


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    tid = user.tenant_id
    n_dossiers = (
        await session.execute(select(func.count()).select_from(Dossier).where(Dossier.tenant_id == tid))
    ).scalar_one()
    n_encours = (
        await session.execute(
            select(func.count())
            .select_from(Dossier)
            .where(
                Dossier.tenant_id == tid,
                Dossier.status.in_(("draft", "analyzing", "generating", "review")),
            )
        )
    ).scalar_one()
    n_pat = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tid, Document.doc_role == "patrimoine")
        )
    ).scalar_one()
    n_dao = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.tenant_id == tid, Document.doc_role.in_(("dao_courant", "dao_archive")))
        )
    ).scalar_one()
    n_ex = (
        await session.execute(
            select(func.count())
            .select_from(ExigenceRow)
            .join(Dossier, ExigenceRow.dossier_id == Dossier.id)
            .where(Dossier.tenant_id == tid, ExigenceRow.statut == "a_couvrir")
        )
    ).scalar_one()
    n_exports = (
        await session.execute(
            select(func.count())
            .select_from(Export)
            .join(Dossier, Export.dossier_id == Dossier.id)
            .where(Dossier.tenant_id == tid)
        )
    ).scalar_one()
    role = user.role if user.role in _HEADLINES else "redacteur"
    return DashboardSummary(
        role=role,
        dossiers=n_dossiers or 0,
        dossiers_en_cours=n_encours or 0,
        documents_patrimoine=n_pat or 0,
        documents_dao=n_dao or 0,
        exigences_a_couvrir=n_ex or 0,
        exports_count=n_exports or 0,
        headline=_HEADLINES[role],
        focus=_FOCUS[role],
    )

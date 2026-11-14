"""Dossier conversationnel : plan, générations, export multi-format MinIO."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from io import BytesIO
from uuid import UUID

from docx import Document as DocxDocument
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Conversation, Dossier, ExigenceRow, ExigenceSection, Export, Generation, OutlineItem
from app.services.minio_client import get_minio
from app.services.pdf_export import build_pdf, sections_from_pairs
from app.workflow.sections import archetype_for_key

log = logging.getLogger("btp.dossier")

EXPORT_FORMATS = ("docx", "pdf", "md", "txt")
MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}
EXT = {"docx": "docx", "pdf": "pdf", "md": "md", "txt": "txt"}


class DossierRequisError(ValueError):
    """Levée quand une action (rédaction, export, dépôt de pièce scopée) est
    tentée sur une conversation qui n'est associée à aucun dossier.

    Un dossier se crée désormais UNIQUEMENT via `POST /dossiers`, DAO chargé
    puis analysé (§9) — plus jamais en sous-produit lazy d'une conversation
    avec un outline générique inventé avant lecture du DAO."""


async def require_dossier(session: AsyncSession, conv: Conversation) -> Dossier:
    if conv.dossier_id:
        doss = await session.get(Dossier, conv.dossier_id)
        if doss is not None:
            return doss
    raise DossierRequisError(
        "Cette conversation n'est associée à aucun dossier. Créez d'abord un dossier "
        "(Dossiers AO → Nouveau dossier), chargez son DAO, puis démarrez la conversation "
        "depuis ce dossier."
    )


async def ensure_outline_item(
    session: AsyncSession, dossier_id: UUID, key: str, title: str
) -> OutlineItem:
    row = (
        await session.execute(
            select(OutlineItem).where(OutlineItem.dossier_id == dossier_id, OutlineItem.key == key)
        )
    ).scalar_one_or_none()
    if row:
        return row
    max_ord = (
        await session.execute(
            select(func.coalesce(func.max(OutlineItem.sort_order), -1)).where(
                OutlineItem.dossier_id == dossier_id
            )
        )
    ).scalar_one()
    row = OutlineItem(
        dossier_id=dossier_id,
        key=key,
        heading_level=1,
        title=title,
        sort_order=int(max_ord) + 1,
        status="todo",
        archetype=archetype_for_key(key),
    )
    session.add(row)
    await session.flush()
    return row


async def latest_section_markdown(session: AsyncSession, dossier_id: UUID, section_key: str) -> str | None:
    """Texte de la dernière version d'une section, ou None si jamais générée
    — utilisé pour enrichir une section existante depuis la conversation
    (§ ajouter du contenu, plutôt que régénérer à l'aveugle)."""
    gen = (
        await session.execute(
            select(Generation)
            .where(Generation.dossier_id == dossier_id, Generation.section_key == section_key)
            .order_by(Generation.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if gen is None:
        return None
    return (gen.content or {}).get("texte")


async def active_exigences_for_section(session: AsyncSession, outline_item_id: UUID) -> list[dict]:
    """Exigences actives (proposées ou confirmées, jamais exclues) liées à
    cette section — à injecter dans generate_section() pour que la
    rédaction traite VRAIMENT les exigences du DAO, pas juste le contexte
    patrimoine générique remonté par la recherche agentique."""
    rows = (
        await session.execute(
            select(ExigenceRow)
            .join(ExigenceSection, ExigenceSection.exigence_id == ExigenceRow.id)
            .where(ExigenceSection.outline_item_id == outline_item_id, ExigenceSection.statut != "exclue")
        )
    ).scalars().all()
    return [{"id": str(e.id), "libelle": e.libelle, "type": e.type} for e in rows]


async def save_generation(
    session: AsyncSession,
    *,
    dossier: Dossier,
    section_key: str,
    title: str,
    texte: str,
    citations: list,
    model: str,
    content: dict | None = None,
    context_snapshot: dict | None = None,
    exigences_couvertes: list | None = None,
) -> Generation:
    """`content` : passer le dump complet de `SectionGeneree` (V2, blocs +
    citations + abstentions) pour une persistance structurée — sinon repli
    sur l'ancien format {"titre", "texte"} (compat V1)."""
    item = await ensure_outline_item(session, dossier.id, section_key, title)
    last_v = (
        await session.execute(
            select(func.coalesce(func.max(Generation.version), 0)).where(
                Generation.dossier_id == dossier.id,
                Generation.section_key == section_key,
            )
        )
    ).scalar_one()
    gen = Generation(
        dossier_id=dossier.id,
        section_key=section_key,
        content=content if content is not None else {"titre": title, "texte": texte},
        citations=citations or [],
        context_snapshot=context_snapshot or {},
        exigences_couvertes=exigences_couvertes or [],
        model=model,
        version=int(last_v) + 1,
    )
    session.add(gen)
    item.status = "generated"
    item.title = title
    item.updated_at = datetime.now(UTC)
    dossier.status = "generating"
    dossier.updated_at = datetime.now(UTC)
    await session.flush()
    log.info("génération enregistrée dossier=%s section=%s v=%s", dossier.id, section_key, gen.version)
    return gen


async def latest_sections(session: AsyncSession, dossier_id: UUID) -> list[tuple[OutlineItem, Generation | None]]:
    items = (
        await session.execute(
            select(OutlineItem)
            .where(OutlineItem.dossier_id == dossier_id)
            .order_by(OutlineItem.sort_order)
        )
    ).scalars().all()
    out: list[tuple[OutlineItem, Generation | None]] = []
    for item in items:
        gen = (
            await session.execute(
                select(Generation)
                .where(
                    Generation.dossier_id == dossier_id,
                    Generation.section_key == item.key,
                )
                .order_by(Generation.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        out.append((item, gen))
    return out


def _rows_from_pairs(pairs) -> tuple[list[tuple[str, str]], list[str]]:
    rows: list[tuple[str, str]] = []
    keys: list[str] = []
    for item, gen in pairs:
        if gen is None:
            continue
        titre = (gen.content or {}).get("titre") or item.title
        texte = (gen.content or {}).get("texte") or ""
        rows.append((titre, texte))
        keys.append(item.key)
    return rows, keys


def _build_markdown(*, project_name: str, rows: list[tuple[str, str]], transcript: str | None) -> bytes:
    lines = [f"# {project_name or 'Mémoire technique'}", ""]
    if not rows and transcript:
        lines.extend(["## Brouillon", "", transcript, ""])
    for title, texte in rows:
        lines.extend([f"## {title}", "", texte or "", ""])
    return "\n".join(lines).encode("utf-8")


def _build_txt(*, project_name: str, rows: list[tuple[str, str]], transcript: str | None) -> bytes:
    lines = [project_name or "Mémoire technique", "=" * 40, ""]
    if not rows and transcript:
        lines.extend(["Brouillon", transcript, ""])
    for title, texte in rows:
        lines.extend([title, "-" * len(title), texte or "", ""])
    return "\n".join(lines).encode("utf-8")


def _build_docx(*, project_name: str, rows: list[tuple[str, str]], transcript: str | None) -> bytes:
    doc = DocxDocument()
    doc.add_heading(project_name or "Mémoire technique", 0)
    if not rows and transcript:
        doc.add_heading("Brouillon", 1)
        doc.add_paragraph(transcript)
    for title, texte in rows:
        doc.add_heading(title, 1)
        for para in (texte or "").split("\n"):
            if para.strip():
                doc.add_paragraph(para.strip())
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _render_export(
    fmt: str,
    *,
    project_name: str,
    rows: list[tuple[str, str]],
    transcript: str | None,
    sections: list[dict] | None = None,
    version: int = 1,
) -> bytes:
    if fmt == "docx":
        return _build_docx(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "md":
        return _build_markdown(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "txt":
        return _build_txt(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "pdf":
        return build_pdf(
            project_name=project_name, sections=sections or [], transcript=transcript, version=version
        )
    raise ValueError(f"format inconnu : {fmt}")


async def export_document(
    session: AsyncSession,
    *,
    dossier: Dossier,
    user,
    fmt: str = "docx",
    transcript: str | None = None,
) -> tuple[Export, bytes]:
    if fmt not in EXPORT_FORMATS:
        raise ValueError(f"Format {fmt!r} non supporté")
    version = int(dossier.current_version or 1)
    pairs = await latest_sections(session, dossier.id)
    rows, keys = _rows_from_pairs(pairs)
    data = _render_export(
        fmt,
        project_name=dossier.project_name or "Mémoire",
        rows=rows,
        transcript=transcript,
        sections=sections_from_pairs(pairs) if fmt == "pdf" else None,
        version=version,
    )
    settings = get_settings()
    ext = EXT[fmt]
    object_key = f"{dossier.tenant_id}/exports/{dossier.id}/v{version}.{ext}"
    log.info("export %s DÉBUT key=%s octets=%s sections=%s", fmt, object_key, len(data), keys)
    get_minio().put_object(
        settings.minio_bucket_export,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=MIME[fmt],
    )
    rec = Export(
        dossier_id=dossier.id,
        version=version,
        format=fmt,
        object_key=object_key,
        size_bytes=len(data),
        sections_included=keys,
        exported_by=user.id,
    )
    session.add(rec)
    dossier.current_version = version + 1
    dossier.status = "exported"
    dossier.updated_at = datetime.now(UTC)
    await session.flush()
    log.info("export %s FIN id=%s version=%s", fmt, rec.id, version)
    return rec, data


async def export_docx(session, *, dossier, user, transcript=None):
    return await export_document(session, dossier=dossier, user=user, fmt="docx", transcript=transcript)


def preview_markdown_from_sections(rows: list[tuple[str, str]], project_name: str) -> str:
    return _build_markdown(project_name=project_name, rows=rows, transcript=None).decode("utf-8")

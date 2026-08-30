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
from app.models.sql import Conversation, Dossier, Export, Generation, OutlineItem
from app.services.minio_client import get_minio
from app.workflow.sections import DEFAULT_OUTLINE, archetype_for_key

log = logging.getLogger("btp.dossier")

EXPORT_FORMATS = ("docx", "pdf", "md", "txt")
MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
}
EXT = {"docx": "docx", "pdf": "pdf", "md": "md", "txt": "txt"}


async def ensure_dossier(session: AsyncSession, conv: Conversation, user) -> Dossier:
    if conv.dossier_id:
        doss = await session.get(Dossier, conv.dossier_id)
        if doss is not None:
            return doss
    doss = Dossier(
        tenant_id=user.tenant_id,
        created_by=user.id,
        project_name=conv.title or "Mémoire conversation",
        status="generating",
    )
    session.add(doss)
    await session.flush()
    for i, (key, level, title) in enumerate(DEFAULT_OUTLINE):
        session.add(
            OutlineItem(
                dossier_id=doss.id,
                key=key,
                heading_level=level,
                title=title,
                sort_order=i,
                status="todo",
                archetype=archetype_for_key(key),
            )
        )
    conv.dossier_id = doss.id
    await session.flush()
    log.info("dossier créé id=%s conversation=%s", doss.id, conv.id)
    return doss


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


async def _section_rows(session: AsyncSession, dossier_id: UUID) -> tuple[list[tuple[str, str]], list[str]]:
    pairs = await latest_sections(session, dossier_id)
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


def _build_pdf(*, project_name: str, rows: list[tuple[str, str]], transcript: str | None) -> bytes:
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleFr", parent=styles["Title"], fontName="Helvetica-Bold", spaceAfter=14)
    h2_style = ParagraphStyle("H2Fr", parent=styles["Heading2"], fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle("BodyFr", parent=styles["Normal"], fontName="Helvetica", leading=14, spaceAfter=6)

    def esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

    story: list = [Paragraph(esc(project_name or "Mémoire technique"), title_style), Spacer(1, 0.3 * cm)]
    if transcript and not rows:
        story.append(Paragraph(esc("Brouillon"), h2_style))
        story.append(Paragraph(esc(transcript), body_style))
    for title, texte in rows:
        story.append(Paragraph(esc(title), h2_style))
        for para in (texte or "").split("\n"):
            if para.strip():
                story.append(Paragraph(esc(para.strip()), body_style))
        story.append(Spacer(1, 0.2 * cm))
    doc.build(story)
    return buf.getvalue()


def _render_export(fmt: str, *, project_name: str, rows: list[tuple[str, str]], transcript: str | None) -> bytes:
    if fmt == "docx":
        return _build_docx(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "md":
        return _build_markdown(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "txt":
        return _build_txt(project_name=project_name, rows=rows, transcript=transcript)
    if fmt == "pdf":
        return _build_pdf(project_name=project_name, rows=rows, transcript=transcript)
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
    rows, keys = await _section_rows(session, dossier.id)
    data = _render_export(
        fmt,
        project_name=dossier.project_name or "Mémoire",
        rows=rows,
        transcript=transcript,
    )
    version = int(dossier.current_version or 1)
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

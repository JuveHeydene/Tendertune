"""Compilation des pièces administratives d'un dossier en un seul PDF —
« exporter un document », pas une liste de fichiers à retélécharger un par
un pour les recoller soi-même avant dépôt sur la plateforme de l'acheteur.

Fusion best-effort : un PDF s'insère page à page, une image devient une
page ; un format non convertible (rare pour ce type de pièces — surtout du
PDF ou du scan) reçoit une page de repli explicite plutôt que d'être omis
silencieusement ou de faire planter tout l'export.

Pillow + pypdf uniquement (PAS pymupdf/fitz, réservé à l'extra OCR absent
de l'image API — voir pyproject.toml) : Pillow est de toute façon garanti
présent, dépendance transitive de weasyprint (export mémoire, §dossier_
workflow), mais déclaré explicitement ici puisqu'utilisé directement.
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.sql import Document, Dossier, DossierPiece
from app.services.minio_client import get_minio

log = logging.getLogger("btp.pieces_export")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".bmp"}
_PAGE_SIZE = (1240, 1754)  # ~A4 à 150dpi
_MARGIN = 90


def _wrap_line(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Un long titre (nom de projet, libellé de pièce) dépasse largement la
    largeur de page sans retour à la ligne manuel — le centrer tel quel le
    fait déborder hors page des deux côtés. Découpe mot par mot."""
    words = line.split(" ")
    wrapped: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width or not current:
            current = candidate
        else:
            wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)
    return wrapped


def _title_page_pdf(text: str, *, fontsize: int = 40) -> bytes:
    img = Image.new("RGB", _PAGE_SIZE, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=fontsize)
    max_width = _PAGE_SIZE[0] - 2 * _MARGIN
    lines: list[str] = []
    for raw_line in text.split("\n"):
        lines.extend(_wrap_line(draw, raw_line, font, max_width))

    total_h = sum(draw.textbbox((0, 0), line, font=font)[3] for line in lines) + (len(lines) - 1) * 12
    y = max((_PAGE_SIZE[1] - total_h) / 2, _MARGIN)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text((max((_PAGE_SIZE[0] - w) / 2, _MARGIN), y), line, fill="black", font=font)
        y += bbox[3] - bbox[1] + 12
    buf = BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


def _append_pdf_pages(writer: PdfWriter, buf: BytesIO) -> None:
    for page in PdfReader(buf).pages:
        writer.add_page(page)


def _append_title(writer: PdfWriter, text: str, *, fontsize: int = 40) -> None:
    _append_pdf_pages(writer, BytesIO(_title_page_pdf(text, fontsize=fontsize)))


def _append_pdf_bytes(writer: PdfWriter, data: bytes) -> bool:
    try:
        _append_pdf_pages(writer, BytesIO(data))
        return True
    except Exception:
        return False


def _append_image_bytes(writer: PdfWriter, data: bytes) -> bool:
    try:
        img = Image.open(BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="PDF")
        _append_pdf_pages(writer, buf)
        return True
    except Exception:
        return False


async def build_pieces_pdf(session: AsyncSession, dossier: Dossier) -> tuple[bytes, list[str]]:
    """Retourne (pdf_bytes, libellés des pièces sans fichier fourni)."""
    pieces = (
        await session.execute(
            select(DossierPiece).where(DossierPiece.dossier_id == dossier.id).order_by(DossierPiece.libelle)
        )
    ).scalars().all()

    settings = get_settings()
    minio = get_minio()
    writer = PdfWriter()
    missing: list[str] = []

    _append_title(writer, dossier.project_name or "Dossier administratif", fontsize=56)

    for piece in pieces:
        doc = await session.get(Document, piece.document_id) if piece.document_id else None
        if doc is None:
            missing.append(piece.libelle)
            continue

        _append_title(writer, piece.libelle + ("" if piece.obligatoire else " (optionnel)"))

        try:
            response = minio.get_object(settings.minio_bucket_raw, doc.object_key)
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:
            log.warning("build_pieces_pdf — lecture MinIO échouée pour %s : %s", doc.filename, exc)
            _append_title(writer, f"Fichier illisible : {doc.filename}\n(à joindre manuellement)", fontsize=28)
            continue

        ext = Path(doc.filename or "").suffix.lower()
        ok = _append_pdf_bytes(writer, data) if ext == ".pdf" else False
        if not ok and ext in IMAGE_EXTENSIONS:
            ok = _append_image_bytes(writer, data)
        if not ok:
            _append_title(
                writer,
                f"« {doc.filename} » — format non convertible\nautomatiquement en PDF.\n"
                "À joindre manuellement au dossier de dépôt.",
                fontsize=28,
            )

    if len(writer.pages) <= 1:
        _append_title(writer, "Aucune pièce fournie pour ce dossier.", fontsize=32)

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue(), missing

"""Extraction de texte : Docling (si installé) > Paddle OCR (scan) > pypdf / docx / xlsx."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

# Rappelé après chaque page OCRisée : (numéro de page, texte, confiance).
# Permet à l'appelant (app/workers/ingest.py) de persister la progression
# page par page, pour reprendre après une interruption (timeout de tâche,
# crash worker) sans refaire les pages déjà traitées.
OnPageDone = Callable[[int, str, "float | None"], None]

log = logging.getLogger("btp.parse")

PDF_TEXT_MIN_CHARS_PER_PAGE = 40


@dataclass
class ParsedPage:
    page: int | None
    text: str
    heading_path: str | None = None 


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    ocr_used: bool = False
    ocr_confidence: float | None = None
    parser: str = "unknown"
    page_count: int | None = None 


def parse_file(
    path: str,
    filename: str,
    mime: str | None,
    *,
    resume_progress: dict | None = None,
    on_page_done: OnPageDone | None = None,
) -> ParsedDocument:
    suffix = Path(filename).suffix.lower()
    raw = Path(path).read_bytes()[:8]

    if suffix in {".xlsx", ".xlsm"} or (mime or "").endswith("spreadsheetml.sheet"):
        log.info("route parse → openpyxl (%s)", filename)
        return _parse_xlsx(path)
    if suffix in {".docx"} or (mime or "").endswith("wordprocessingml.document"):
        log.info("route parse → python-docx (%s)", filename)
        return _parse_docx(path)
    if suffix in {".txt", ".md"}:
        log.info("route parse → plaintext (%s)", filename)
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return ParsedDocument(pages=[ParsedPage(1, text)], parser="plaintext", page_count=1)
    if suffix == ".pdf" or raw.startswith(b"%PDF"):
        log.info("route parse → PDF (%s)", filename)
        return _parse_pdf(path, resume_progress=resume_progress, on_page_done=on_page_done)

    if suffix in IMAGE_SUFFIXES:
        return _parse_image(path, filename)

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError(f"Format non géré : {filename}")
    return ParsedDocument(pages=[ParsedPage(1, text)], parser="fallback-text", page_count=1)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}

# Seuil identique à PDF_TEXT_MIN_CHARS_PER_PAGE : en dessous, l'image est
# traitée comme un ACTIF VISUEL (photo de chantier, logo) et non comme un
# document texte scanné. Ce n'est PAS un échec d'ingestion (§5.2,
# Nouvelle_Architecture/base_de_donnees_et_interface.md) : le document passe
# quand même à status="ready", simplement avec 0 chunk — il reste attachable
# à un export DOCX (SectionGeneree.blocs[].type="image") mais jamais indexé
# en texte / cherché en RAG.
IMAGE_TEXT_MIN_CHARS = 40


def _parse_image(path: str, filename: str) -> ParsedDocument:
    """Image uploadée directement (pas une page de PDF rasterisée).

    Bug V1 corrigé ici : le moteur OCR (_try_paddle → _paddle_run) savait déjà
    traiter une image en entrée directe (branche `else` de _paddle_run, qui
    traite le fichier comme une page unique sans rasterisation) — seul le
    routage de parse_file() ne reconnaissait aucun format image et levait
    `ValueError("Format non géré")`. Voir Diagramme 1, Nouvelle_Architecture/
    diagrammes_sequence_v2.txt.
    """
    log.info("route parse → image directe (%s)", filename)
    parsed = _try_paddle(path)
    if parsed is None or not parsed.pages:
        log.info("Image sans texte OCR exploitable (%s) — actif visuel", filename)
        return ParsedDocument(pages=[], parser="image-actif-visuel", page_count=0)

    total_chars = sum(len(p.text) for p in parsed.pages)
    if total_chars < IMAGE_TEXT_MIN_CHARS:
        log.info(
            "Image avec peu de texte (%d car. < %d) (%s) — actif visuel",
            total_chars,
            IMAGE_TEXT_MIN_CHARS,
            filename,
        )
        return ParsedDocument(pages=[], parser="image-actif-visuel", page_count=0)

    return parsed


def _parse_docx(path: str) -> ParsedDocument:
    from docx import Document as Docx

    doc = Docx(path)
    blocks: list[ParsedPage] = []
    heading = None
    buf: list[str] = []
    for p in doc.paragraphs:
        style = (p.style.name or "") if p.style else ""
        if style.startswith("Heading"):
            if buf:
                blocks.append(ParsedPage(None, "\n".join(buf), heading))
                buf = []
            heading = p.text.strip() or heading
        elif p.text.strip():
            buf.append(p.text)
    if buf:
        blocks.append(ParsedPage(None, "\n".join(buf), heading))
    if not blocks:
        raise ValueError("DOCX vide")
    return ParsedDocument(pages=blocks, parser="python-docx", page_count=len(blocks))


def _parse_xlsx(path: str) -> ParsedDocument:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    pages: list[ParsedPage] = []
    for sheet in wb.worksheets:
        lines = [f"# {sheet.title}"]
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i > 400:
                lines.append("… (lignes suivantes omises)")
                break
            cells = ["" if c is None else str(c) for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
        pages.append(ParsedPage(None, "\n".join(lines), sheet.title))
    wb.close()
    return ParsedDocument(pages=pages, parser="openpyxl", page_count=len(pages))


def _parse_pdf(
    path: str,
    *,
    resume_progress: dict | None = None,
    on_page_done: OnPageDone | None = None,
) -> ParsedDocument:
    digital = _parse_pdf_pypdf(path)
    density = _chars_per_page(digital)
    log.info("PDF pypdf densité=%.1f car/page (seuil=%s)", density, PDF_TEXT_MIN_CHARS_PER_PAGE)
    if density >= PDF_TEXT_MIN_CHARS_PER_PAGE:
        docling = _try_docling(path)
        if docling is not None:
            log.info("PDF : Docling retenu (texte digital)")
            return docling
        log.info("PDF : pypdf retenu (Docling absent ou vide)")
        return digital

    paddle = _try_paddle(path, resume_progress=resume_progress, on_page_done=on_page_done)
    if paddle is not None:
        log.info("PDF scan : PaddleOCR retenu")
        return paddle
    docling = _try_docling(path)
    if docling is not None:
        log.info("PDF scan : Docling retenu (Paddle absent)")
        return docling
    if digital.pages and any(p.text.strip() for p in digital.pages):
        log.warning("PDF peu de texte : on garde pypdf quand même")
        digital.parser = "pypdf-sparse"
        return digital
    raise ValueError(
        "PDF scan détecté et PaddleOCR/Docling absents. "
        "Installer : uv sync --extra ingest  et/ou  --extra ocr"
    )


def _chars_per_page(parsed: ParsedDocument) -> float:
    if not parsed.pages:
        return 0.0
    total = sum(len(p.text) for p in parsed.pages)
    return total / max(len(parsed.pages), 1)


def _parse_pdf_pypdf(path: str) -> ParsedDocument:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "pypdf absent dans l’image worker — rebuild : "
            "docker compose --profile dev build api && up -d api worker"
        ) from exc

    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages, start=1):
        pages.append(ParsedPage(i, page.extract_text() or "", None))
    return ParsedDocument(pages=pages, parser="pypdf", page_count=len(pages))


def _try_docling(path: str) -> ParsedDocument | None:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        log.info("Docling non installé — skip")
        return None
    try:
        conv = DocumentConverter()
        result = conv.convert(path)
        md = result.document.export_to_markdown()
        if not md.strip():
            return None
        return ParsedDocument(
            pages=[ParsedPage(None, md, None)],
            parser="docling",
            page_count=getattr(result.document, "num_pages", None),
        )
    except Exception as exc:
        log.warning("Docling indisponible ou échec (%s) — repli parseur suivant", exc)
        return None


def _pdf_page_image_paths(path: str, dpi: int = 200) -> list[tuple[int, str]]:
    """Rasterise un PDF page par page (PaddleOCR attend des images, pas un PDF)."""
    try:
        import fitz  # pymupdf
    except ImportError:
        log.warning("pymupdf absent — impossible de rasteriser le PDF pour PaddleOCR")
        return []
    import tempfile

    doc = fitz.open(path)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    out: list[tuple[int, str]] = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=mat, alpha=False)
        tmp = tempfile.NamedTemporaryFile(suffix=f"-p{i}.png", delete=False)
        tmp.close()
        pix.save(tmp.name)
        out.append((i, tmp.name))
    doc.close()
    return out


def _resume_pages_dict(resume_progress: dict | None) -> dict[int, tuple[str, float | None]]:
    """Convertit documents.ocr_progress (clés JSON = str) en {page_int: (texte, confiance)}."""
    if not resume_progress:
        return {}
    raw_pages = resume_progress.get("pages") or {}
    out: dict[int, tuple[str, float | None]] = {}
    for key, value in raw_pages.items():
        try:
            page_num = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            out[page_num] = (value.get("text") or "", value.get("confidence"))
    return out


def _paddle_ocr_pages(
    ocr,
    image_paths: list[tuple[int, str]],
    *,
    parser: str,
    cleanup: bool = True,
    resume_pages: dict[int, tuple[str, float | None]] | None = None,
    on_page_done: OnPageDone | None = None,
) -> ParsedDocument | None:
    from pathlib import Path

    resume_pages = resume_pages or {}
    pages: list[ParsedPage] = []
    confs: list[float] = []
    n_resumed = 0
    for page_num, img_path in image_paths:
        if page_num in resume_pages:
            # Déjà OCRisée lors d'une tentative précédente (reprise après
            # timeout de tâche ou crash worker) — on réutilise le résultat
            # au lieu de refaire l'inférence, potentiellement coûteuse.
            text, conf = resume_pages[page_num]
            if cleanup:
                Path(img_path).unlink(missing_ok=True)
            if text:
                pages.append(ParsedPage(page_num, text, None))
                if conf is not None:
                    confs.append(conf)
            n_resumed += 1
            continue
        try:
            result = ocr.ocr(img_path, cls=True)
        finally:
            if cleanup:
                Path(img_path).unlink(missing_ok=True)
        lines: list[str] = []
        page_confs: list[float] = []
        # PaddleOCR renvoie parfois [None] (pas juste [] ou None) quand aucune
        # zone de texte n'est détectée sur une page (page de garde, logo, tampon,
        # page blanche) — sans ce `or []`, `result[0]` vaut None et l'itération
        # fait planter TOUT le document au lieu d'ignorer cette seule page.
        page_items = (result[0] if result else None) or []
        for item in page_items:
            if not item or len(item) < 2:
                continue
            txt, conf = item[1][0], float(item[1][1])
            lines.append(txt)
            page_confs.append(conf)
        page_text = "\n".join(lines)
        page_conf = (sum(page_confs) / len(page_confs)) if page_confs else None
        if lines:
            pages.append(ParsedPage(page_num, page_text, None))
            confs.extend(page_confs)
        # Rappelé pour CHAQUE page (même vide) : une page tentée et vide ne
        # doit plus jamais être retentée à la prochaine reprise.
        if on_page_done is not None:
            on_page_done(page_num, page_text, page_conf)
    if n_resumed:
        log.info("PaddleOCR reprise : %s/%s pages réutilisées (déjà OCRisées)", n_resumed, len(image_paths))
    if not pages:
        return None
    avg = sum(confs) / len(confs) if confs else None
    return ParsedDocument(
        pages=pages,
        ocr_used=True,
        ocr_confidence=avg,
        parser=parser,
        page_count=len(pages),
    )


def _paddle_run(
    path: str,
    *,
    use_gpu: bool,
    resume_progress: dict | None = None,
    on_page_done: OnPageDone | None = None,
) -> ParsedDocument | None:
    from paddleocr import PaddleOCR

    raw = Path(path).read_bytes()[:8]
    is_pdf = Path(path).suffix.lower() == ".pdf" or raw.startswith(b"%PDF")
    parser = "paddleocr-gpu" if use_gpu else "paddleocr-cpu"
    ocr = PaddleOCR(use_angle_cls=True, lang="fr", use_gpu=use_gpu, show_log=False)
    if is_pdf:
        image_paths = _pdf_page_image_paths(path)
        if not image_paths:
            return None
        return _paddle_ocr_pages(
            ocr,
            image_paths,
            parser=parser,
            cleanup=True,
            resume_pages=_resume_pages_dict(resume_progress),
            on_page_done=on_page_done,
        )
    return _paddle_ocr_pages(ocr, [(1, path)], parser=parser, cleanup=False)


def _try_paddle(
    path: str,
    *,
    resume_progress: dict | None = None,
    on_page_done: OnPageDone | None = None,
) -> ParsedDocument | None:
    try:
        from paddleocr import PaddleOCR  # noqa: F401
    except ImportError:
        log.info("PaddleOCR non installé — skip")
        return None
    settings = get_settings()
    modes = [True, False] if settings.use_gpu else [False]
    for use_gpu in modes:
        label = "GPU" if use_gpu else "CPU"
        log.info("PaddleOCR tentative %s (USE_GPU=%s)", label, settings.use_gpu)
        try:
            parsed = _paddle_run(path, use_gpu=use_gpu, resume_progress=resume_progress, on_page_done=on_page_done)
            if parsed:
                log.info("PaddleOCR %s OK — %s pages", label, parsed.page_count)
                return parsed
        except RuntimeError as exc:
            msg = str(exc).lower()
            if use_gpu and ("cudnn" in msg or "cuda" in msg):
                log.warning("PaddleOCR GPU indisponible (%s) — repli CPU", exc)
                continue
            raise
    return None

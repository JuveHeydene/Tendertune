"""Extraction de texte : Docling (si installé) > Paddle OCR (scan) > pypdf / docx / xlsx."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

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


def parse_file(path: str, filename: str, mime: str | None) -> ParsedDocument:
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
        return _parse_pdf(path)

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError(f"Format non géré : {filename}")
    return ParsedDocument(pages=[ParsedPage(1, text)], parser="fallback-text", page_count=1)


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


def _parse_pdf(path: str) -> ParsedDocument:
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

    paddle = _try_paddle(path)
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


def _paddle_ocr_pages(
    ocr,
    image_paths: list[tuple[int, str]],
    *,
    parser: str,
    cleanup: bool = True,
) -> ParsedDocument | None:
    from pathlib import Path

    pages: list[ParsedPage] = []
    confs: list[float] = []
    for page_num, img_path in image_paths:
        try:
            result = ocr.ocr(img_path, cls=True)
        finally:
            if cleanup:
                Path(img_path).unlink(missing_ok=True)
        lines: list[str] = []
        for item in result[0] if result else []:
            if not item or len(item) < 2:
                continue
            txt, conf = item[1][0], float(item[1][1])
            lines.append(txt)
            confs.append(conf)
        if lines:
            pages.append(ParsedPage(page_num, "\n".join(lines), None))
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


def _paddle_run(path: str, *, use_gpu: bool) -> ParsedDocument | None:
    from paddleocr import PaddleOCR

    raw = Path(path).read_bytes()[:8]
    is_pdf = Path(path).suffix.lower() == ".pdf" or raw.startswith(b"%PDF")
    parser = "paddleocr-gpu" if use_gpu else "paddleocr-cpu"
    ocr = PaddleOCR(use_angle_cls=True, lang="fr", use_gpu=use_gpu, show_log=False)
    if is_pdf:
        image_paths = _pdf_page_image_paths(path)
        if not image_paths:
            return None
        return _paddle_ocr_pages(ocr, image_paths, parser=parser, cleanup=True)
    return _paddle_ocr_pages(ocr, [(1, path)], parser=parser, cleanup=False)


def _try_paddle(path: str) -> ParsedDocument | None:
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
            parsed = _paddle_run(path, use_gpu=use_gpu)
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

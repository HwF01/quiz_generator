from __future__ import annotations

import io
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class ParseResult:
    text: str
    pages: list[str] = field(default_factory=list)
    used_ocr: bool = False
    error: str | None = None


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def parse_pdf(data: bytes) -> ParseResult:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    text = _clean("\n".join(pages))
    used_ocr = False
    if settings.enable_ocr and len(text) < 80:
        ocr_pages = []
        try:
            from app.services.ocr import ocr_pixmap

            for i, page in enumerate(doc):
                if i >= 10:
                    break
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                ocr_pages.append(ocr_pixmap(pix.tobytes("png")))
            ocr_text = _clean("\n".join(ocr_pages))
            if len(ocr_text) > len(text):
                text, pages, used_ocr = ocr_text, ocr_pages, True
        except Exception:
            pass
    if not text.strip():
        return ParseResult(text="", pages=pages, used_ocr=used_ocr, error="未能提取到可选中文本，扫描件请检查或稍后使用 OCR")
    tables = []
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables() or []:
                    rows = [" | ".join(cell or "" for cell in row) for row in table]
                    tables.append("\n".join(rows))
    except Exception:
        pass
    if tables:
        text += "\n\n[表格]\n" + "\n\n".join(tables)
    return ParseResult(text=text, pages=pages, used_ocr=used_ocr)


def parse_docx(data: bytes) -> ParseResult:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    text = _clean("\n".join(parts))
    if not text:
        return ParseResult(text="", error="Word 文档中没有可提取文本")
    return ParseResult(text=text, pages=[text])


def parse_pptx(data: bytes) -> ParseResult:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    pages = []
    for slide in prs.slides:
        texts = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text)
        pages.append(_clean("\n".join(texts)))
    text = _clean("\n\n".join(pages))
    if not text:
        return ParseResult(text="", error="PPT 中没有可提取文本")
    return ParseResult(text=text, pages=pages)


def parse_document(filename: str, data: bytes) -> ParseResult:
    name = filename.lower()
    if name.endswith(".pdf"):
        return parse_pdf(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    if name.endswith(".pptx"):
        return parse_pptx(data)
    if name.endswith(".txt") or name.endswith(".md"):
        text = data.decode("utf-8", errors="ignore")
        return ParseResult(text=_clean(text), pages=[_clean(text)])
    return ParseResult(text="", error="仅支持 PDF / Word / PPT / TXT")

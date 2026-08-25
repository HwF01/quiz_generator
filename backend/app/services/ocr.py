from __future__ import annotations

import io
import os


def ocr_pixmap(png_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return ""
    cmd = os.environ.get("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    image = Image.open(io.BytesIO(png_bytes))
    try:
        return pytesseract.image_to_string(image, lang="chi_sim+eng") or ""
    except Exception:
        return pytesseract.image_to_string(image) or ""

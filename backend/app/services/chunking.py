from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class Chunk:
    id: str
    text: str
    start: int
    end: int


def split_paragraphs(text: str) -> list[Chunk]:
    parts = re.split(r"\n\s*\n", text)
    chunks: list[Chunk] = []
    cursor = 0
    idx = 0
    for part in parts:
        part = part.strip()
        if len(part) < 40:
            cursor = text.find(part, cursor) + len(part) if part else cursor
            continue
        start = text.find(part, cursor)
        if start < 0:
            start = cursor
        end = start + len(part)
        if len(part) > 1800:
            for sub in _window(part, 1400, 200):
                chunks.append(Chunk(id=f"c{idx}", text=sub, start=start, end=start + len(sub)))
                idx += 1
        else:
            chunks.append(Chunk(id=f"c{idx}", text=part, start=start, end=end))
            idx += 1
        cursor = end
        if idx >= settings.max_key_sentences * 2:
            break
    if not chunks and text.strip():
        chunks.append(Chunk(id="c0", text=text[:1600], start=0, end=min(len(text), 1600)))
    return chunks[: settings.max_key_sentences * 2]


def _window(text: str, size: int, overlap: int) -> list[str]:
    out = []
    i = 0
    while i < len(text):
        out.append(text[i : i + size])
        i += max(size - overlap, 1)
    return out

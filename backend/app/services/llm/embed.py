from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

from app.core.config import settings


def _tokenize(text: str) -> list[str]:
    chars = re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text.lower())
    grams = []
    for i in range(len(chars) - 1):
        grams.append(chars[i] + chars[i + 1])
    return grams or chars or [text]


def embed_local(text: str) -> np.ndarray:
    tokens = _tokenize(text)
    vec = np.zeros(256, dtype=np.float32)
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % 256] += 1.0
    norm = np.linalg.norm(vec)
    if norm:
        vec /= norm
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def similarity(a: str, b: str) -> float:
    return cosine(embed_local(a), embed_local(b))


async def embed(text: str) -> np.ndarray:
    if settings.embedding_provider == "openai" and settings.openai_api_key:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": "text-embedding-3-small", "input": text[:8000]},
            )
            resp.raise_for_status()
            return np.array(resp.json()["data"][0]["embedding"], dtype=np.float32)
    return embed_local(text)

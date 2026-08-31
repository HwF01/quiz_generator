from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

HASHED_BACKEND = "hashed-bigram"
DASHSCOPE_BACKEND = "dashscope"
DASHSCOPE_BATCH_SIZE = 10
MAX_EMBED_CHARS = 8000
DEFAULT_DASHSCOPE_MODEL = "text-embedding-v3"


@dataclass(frozen=True)
class EmbeddingThresholds:
    answer_sim: float
    context_sim: float
    pair_sim: float
    rank_target: float
    rank_penalty: float


THRESHOLDS = {
    HASHED_BACKEND: EmbeddingThresholds(
        answer_sim=0.86,
        context_sim=0.12,
        pair_sim=0.9,
        rank_target=0.45,
        rank_penalty=0.82,
    ),
    DASHSCOPE_BACKEND: EmbeddingThresholds(
        # text-embedding-v3 实测：叶绿体中 0.93 / 绿叶体 0.87 应丢，
        # 叶绿体膜 0.86 与线粒体 0.57 应留；跑题 vs 材料 0.33，在场细胞器 ≥0.41。
        answer_sim=0.87,
        context_sim=0.38,
        pair_sim=0.80,
        rank_target=0.55,
        rank_penalty=0.82,
    ),
}


def thresholds_for(backend: str) -> EmbeddingThresholds:
    return THRESHOLDS.get(backend, THRESHOLDS[HASHED_BACKEND])


def uses_dashscope() -> bool:
    provider = (settings.embedding_provider or "auto").strip().lower()
    if provider == "local":
        return False
    if provider in {"auto", "dashscope", "qwen"}:
        return bool((settings.qwen_api_key or "").strip())
    return False


def dashscope_model() -> str:
    model = (settings.embedding_model or "").strip()
    if not model or model == HASHED_BACKEND:
        return DEFAULT_DASHSCOPE_MODEL
    return model


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


def _hashed_vectors(texts: list[str]) -> list[np.ndarray]:
    return [embed_local(text) for text in texts]


async def _embed_dashscope(texts: list[str]) -> list[np.ndarray]:
    from app.services.llm.providers import _post_with_retry

    truncated = [(text or "")[:MAX_EMBED_CHARS] or " " for text in texts]
    url = f"{settings.qwen_base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {settings.qwen_api_key}"}
    model = dashscope_model()
    out: list[np.ndarray] = []
    for start in range(0, len(truncated), DASHSCOPE_BATCH_SIZE):
        batch = truncated[start : start + DASHSCOPE_BATCH_SIZE]
        resp = await _post_with_retry(
            url,
            headers=headers,
            json={"model": model, "input": batch},
        )
        payload = resp.json()
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != len(batch):
            raise ValueError("DashScope embedding 响应条数不匹配")
        by_index: dict[int, np.ndarray] = {}
        for item in items:
            if not isinstance(item, dict) or item.get("embedding") is None:
                raise ValueError("DashScope embedding 缺少向量")
            idx = int(item.get("index", len(by_index)))
            by_index[idx] = np.array(item["embedding"], dtype=np.float32)
        for offset in range(len(batch)):
            vec = by_index.get(offset)
            if vec is None:
                raise ValueError("DashScope embedding 缺少 index")
            out.append(vec)
    if len(out) != len(texts):
        raise ValueError("DashScope embedding 数量不完整")
    return out


async def embed_texts(texts: list[str]) -> tuple[list[np.ndarray], str]:
    if not texts:
        backend = DASHSCOPE_BACKEND if uses_dashscope() else HASHED_BACKEND
        return [], backend
    if not uses_dashscope():
        return _hashed_vectors(texts), HASHED_BACKEND
    try:
        return await _embed_dashscope(texts), DASHSCOPE_BACKEND
    except Exception:
        logger.warning("DashScope embedding 失败，回退 hashed-bigram", exc_info=True)
        return _hashed_vectors(texts), HASHED_BACKEND

from __future__ import annotations

import numpy as np
import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.llm.embed import (
    DASHSCOPE_BACKEND,
    DASHSCOPE_BATCH_SIZE,
    HASHED_BACKEND,
    embed_local,
    embed_texts,
)


def _enable_dashscope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "qwen_api_key", "sk-test")
    monkeypatch.setattr(settings, "qwen_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    monkeypatch.setattr(settings, "embedding_provider", "auto")
    monkeypatch.setattr(settings, "embedding_model", "text-embedding-v3")


@pytest.mark.asyncio
async def test_embed_texts_without_key_uses_hashed_bigram(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "")
    monkeypatch.setattr(settings, "embedding_provider", "auto")
    texts = ["叶绿体", "线粒体"]
    vectors, backend = await embed_texts(texts)
    assert backend == HASHED_BACKEND
    assert len(vectors) == 2
    assert np.allclose(vectors[0], embed_local("叶绿体"))


@pytest.mark.asyncio
async def test_embed_texts_local_provider_ignores_key(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "sk-test")
    monkeypatch.setattr(settings, "embedding_provider", "local")
    _, backend = await embed_texts(["叶绿体"])
    assert backend == HASHED_BACKEND


@pytest.mark.asyncio
async def test_embed_texts_batches_dashscope_requests(monkeypatch):
    _enable_dashscope(monkeypatch)
    calls: list[list[str]] = []

    class _Resp:
        def __init__(self, batch: list[str]):
            self._batch = batch

        def json(self) -> dict:
            return {
                "data": [
                    {"index": i, "embedding": [float(i + 1), 0.0]}
                    for i in range(len(self._batch))
                ]
            }

    async def fake_post(_url, **kwargs):
        batch = list(kwargs["json"]["input"])
        calls.append(batch)
        return _Resp(batch)

    monkeypatch.setattr("app.services.llm.providers._post_with_retry", fake_post)
    texts = [f"t{i}" for i in range(DASHSCOPE_BATCH_SIZE + 2)]
    vectors, backend = await embed_texts(texts)
    assert backend == DASHSCOPE_BACKEND
    assert len(calls) == 2
    assert len(calls[0]) == DASHSCOPE_BATCH_SIZE
    assert len(calls[1]) == 2
    assert len(vectors) == len(texts)
    assert vectors[0].tolist() == [1.0, 0.0]


@pytest.mark.asyncio
async def test_embed_texts_http_error_falls_back_to_hashed(monkeypatch):
    _enable_dashscope(monkeypatch)

    async def boom(*_args, **_kwargs):
        raise AppError("模型服务暂不可用", code=503, status_code=503)

    monkeypatch.setattr("app.services.llm.providers._post_with_retry", boom)
    texts = ["叶绿体"]
    vectors, backend = await embed_texts(texts)
    assert backend == HASHED_BACKEND
    assert np.allclose(vectors[0], embed_local("叶绿体"))

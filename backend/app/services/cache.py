from __future__ import annotations

import hashlib
import json

from app.core.redis import get_redis


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_cache_key(text: str, config: dict) -> str:
    payload = json.dumps({"t": text, "c": config}, ensure_ascii=False, sort_keys=True)
    return "gencache:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_cached_questions(text: str, config: dict) -> list[dict] | None:
    redis = get_redis()
    raw = await redis.get(chunk_cache_key(text, config))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def set_cached_questions(text: str, config: dict, questions: list[dict]) -> None:
    redis = get_redis()
    await redis.set(
        chunk_cache_key(text, config),
        json.dumps(questions, ensure_ascii=False),
        ex=60 * 60 * 24 * 7,
    )


def doc_quiz_cache_key(owner_id: str, content_sha: str, generation_config: dict) -> str:
    payload = json.dumps(
        {"owner_id": owner_id, "content_sha": content_sha, "config": generation_config},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "dochash:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def similar_doc_quiz(
    owner_id: str, content_sha: str, generation_config: dict
) -> str | None:
    try:
        redis = get_redis()
        return await redis.get(doc_quiz_cache_key(owner_id, content_sha, generation_config))
    except Exception:
        return None


async def remember_doc_quiz(
    owner_id: str, content_sha: str, generation_config: dict, quiz_id: str
) -> None:
    try:
        redis = get_redis()
        await redis.set(
            doc_quiz_cache_key(owner_id, content_sha, generation_config),
            quiz_id,
            ex=60 * 60 * 24 * 14,
        )
    except Exception:
        pass

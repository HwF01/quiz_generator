from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.core.exceptions import AppError

_TAVILY_URL = "https://api.tavily.com/search"
_TIMEOUT_SECONDS = 8.0


def topic_queries(key_items: Iterable[dict], subject: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for item in key_items:
        tags = [str(tag).strip() for tag in (item.get("knowledge_tags") or []) if str(tag).strip()]
        if not tags:
            continue
        query = f"{subject} {' '.join(tags[:4])}".strip()
        normalized = " ".join(query.split()).lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            queries.append(query[:160])
        if len(queries) >= 3:
            break
    return queries


async def search_related_knowledge(queries: list[str]) -> list[dict]:
    if not settings.web_search_available:
        raise AppError("未填写 Tavily Key，联网补充不可用；普通出题不受影响", code=503, status_code=503)
    if not queries:
        return []
    payloads = await asyncio.gather(*[_tavily_search(query) for query in queries])
    sources: list[dict] = []
    urls: set[str] = set()
    for results in payloads:
        for result in results:
            url = result["url"]
            if url in urls:
                continue
            urls.add(url)
            sources.append(
                {
                    "id": _source_id(url),
                    "title": result["title"],
                    "url": url,
                    "excerpt": result["content"],
                    "query": result["query"],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "used": False,
                }
            )
    return sources


async def _tavily_search(query: str) -> list[dict]:
    body = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "max_results": settings.tavily_max_results,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_TAVILY_URL, json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise AppError("联网检索暂不可用，请稍后重试", code=503, status_code=503) from exc
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return []
    cleaned = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").strip()
        content = str(result.get("content") or "").strip()
        if url and title and content:
            cleaned.append({"url": url, "title": title, "content": content[:1200], "query": query})
    return cleaned


def _source_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"web-{digest}"

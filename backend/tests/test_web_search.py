import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.cache import remember_doc_quiz, similar_doc_quiz
from app.services.web_search import search_related_knowledge, topic_queries


def test_topic_queries_only_use_derived_tags():
    queries = topic_queries(
        [
            {"knowledge_tags": ["牛顿第二定律", "受力分析"], "quote": "不应被发送的原文"},
            {"knowledge_tags": ["牛顿第二定律"]},
        ],
        "math",
    )
    assert queries == ["math 牛顿第二定律 受力分析", "math 牛顿第二定律"]
    assert all("不应被发送" not in query for query in queries)


@pytest.mark.asyncio
async def test_web_search_requires_configured_provider(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "")
    with pytest.raises(AppError, match="尚未配置"):
        await search_related_knowledge(["math 极限"])


@pytest.mark.asyncio
async def test_web_results_are_deduplicated_and_identified(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")

    async def _search(query: str):
        return [
            {
                "url": "https://docs.example.test/topic",
                "title": "参考资料",
                "content": "可靠摘要",
                "query": query,
            }
        ]

    monkeypatch.setattr("app.services.web_search._tavily_search", _search)
    sources = await search_related_knowledge(["math 极限", "math 导数"])
    assert len(sources) == 1
    assert sources[0]["id"].startswith("web-")
    assert sources[0]["used"] is False


@pytest.mark.asyncio
async def test_generation_cache_is_scoped_to_owner_and_config(fake_redis):
    config = {"blueprint": {"total_questions": 5}, "subject": "math"}
    await remember_doc_quiz("user-a", "same-hash", config, "quiz-a")
    assert await similar_doc_quiz("user-a", "same-hash", config) == "quiz-a"
    assert await similar_doc_quiz("user-b", "same-hash", config) is None
    assert await similar_doc_quiz("user-a", "same-hash", {**config, "subject": "it"}) is None

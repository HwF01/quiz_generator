import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.cache import remember_doc_quiz, similar_doc_quiz
from app.services.llm.providers import _mock_json
from app.services.quiz_generator import valid_stem_payload
from app.services.web_search import search_related_knowledge, topic_queries


def test_mock_classify_uses_exam_text_not_prompt():
    blob = (
        "判断科目\n从以下类别中选一个 subject：civics, history, it\n"
        "IT、编程、软件工程；人文社科、历史、政治\nconfidence civics\n"
        "【待考查文本开始】\n光合作用是绿色植物利用光能的过程。\n【待考查文本结束】\n"
    )
    data = _mock_json(blob)
    assert data["subject"] == "general"


def test_mock_extract_quotes_come_from_exam_text():
    passage = "光合作用是绿色植物利用光能的过程。叶绿体是光反应的主要场所。"
    blob = (
        "从适切的文本中抽取 1-3 个关键句\n"
        "answer_type\n不要输出完整选择题\n"
        f"【待考查文本开始】\n{passage}\n【待考查文本结束】\n"
    )
    data = _mock_json(blob)
    quotes = [item["quote"] for item in data["items"]]
    assert quotes
    assert all(quote in passage for quote in quotes)
    assert any("光合" in tag for item in data["items"] for tag in item["knowledge_tags"])


def test_mock_stem_cites_external_sources():
    blob = (
        "不要输出干扰项\n题型：single_choice\n"
        "【待考查文本开始】\n光合作用是绿色植物利用光能的过程。\n【待考查文本结束】\n"
        "【外部参考资料开始】\n"
        '[{"id": "web-abc123", "title": "光合", "url": "https://example.test"}]\n'
        "【外部参考资料结束】\n"
    )
    data = _mock_json(blob)
    assert data["external_source_ids"] == ["web-abc123"]


def test_mock_stem_multi_choice_has_two_correct_texts():
    blob = (
        "不要输出干扰项\n题型：multi_choice\n"
        "【待考查文本开始】\n光合作用是绿色植物利用光能的过程。叶绿体是光反应的主要场所。\n【待考查文本结束】\n"
    )
    data = _mock_json(blob)
    assert data["type"] == "multi_choice"
    assert isinstance(data.get("correct_texts"), list)
    assert len(data["correct_texts"]) == 2
    assert len(set(data["correct_texts"])) == 2
    assert all(str(text).strip() for text in data["correct_texts"])


def test_valid_stem_payload_multi_choice_requires_two_distinct_texts():
    passage = "叶绿体进行光合作用。线粒体进行呼吸作用。"
    base = {
        "stem": "下列哪些是细胞器？",
        "type": "multi_choice",
        "explanation": "二者都是细胞器。",
        "source_quote": "叶绿体进行光合作用。线粒体进行呼吸作用。",
    }
    assert valid_stem_payload({**base, "correct_texts": ["叶绿体", "线粒体"]}, passage)
    assert not valid_stem_payload({**base, "correct_texts": ["叶绿体"]}, passage)
    assert not valid_stem_payload({**base, "correct_texts": ["叶绿体", "叶绿体"]}, passage)


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
    with pytest.raises(AppError, match="Tavily Key"):
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

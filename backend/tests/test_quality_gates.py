import pytest

from app.services.quality_gates import answer_exists, apply_gates, stem_leaks_answer, unique_correct
from app.services.knowledge_tracing import update_mastery, recommend_difficulty


def test_answer_exists_and_leak():
    q = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [
            {"key": "A", "text": "叶绿体"},
            {"key": "B", "text": "线粒体"},
        ],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "source_span": {"quote": "光合作用发生在叶绿体中"},
        "explanation": "叶绿体是场所",
    }
    assert answer_exists(q)
    assert unique_correct(q)
    assert not stem_leaks_answer(q)
    leak_q = {**q, "content": "光合作用主要发生在叶绿体吗？"}
    assert stem_leaks_answer(leak_q)


def test_answer_exists_unrelated_quote():
    q = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [
            {"key": "A", "text": "叶绿体"},
            {"key": "B", "text": "线粒体"},
        ],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "source_span": {"quote": "The capital of France is Paris."},
        "explanation": "叶绿体是场所",
    }
    assert not answer_exists(q)


@pytest.mark.asyncio
async def test_critic_error_forces_review(monkeypatch):
    q = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [
            {"key": "A", "text": "叶绿体"},
            {"key": "B", "text": "线粒体"},
        ],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "source_span": {"quote": "光合作用发生在叶绿体中"},
    }

    async def _boom(*_a, **_k):
        raise RuntimeError("critic down")

    monkeypatch.setattr("app.services.quality_gates.complete_json", _boom)
    out = await apply_gates(q, "光合作用发生在叶绿体中")
    assert out["needs_review"] is True
    scores = out["quality_scores"]
    assert scores["critic_error"] is True
    assert scores["usability"] == 0
    assert scores["answer_exists"] is False


def test_bkt_increases_on_correct():
    p0 = 0.2
    p1 = update_mastery(p0, True)
    assert p1 > p0
    assert recommend_difficulty({"detail": 0.2}, "detail") == "easy"
    assert recommend_difficulty({"detail": 0.85}, "detail") == "hard"

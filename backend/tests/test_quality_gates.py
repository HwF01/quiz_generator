import pytest

from app.services.quality_gates import (
    answer_exists,
    apply_gates,
    choice_structure_valid,
    stem_leaks_answer,
    unique_correct,
)
from app.services.knowledge_tracing import update_mastery, recommend_difficulty
from app.services.subjective_grading import rubric_valid


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


def test_choice_structure_requires_four_distinct_options_and_one_key():
    question = {
        "type": "single_choice",
        "options": [
            {"key": "A", "text": "叶绿体"},
            {"key": "B", "text": "线粒体"},
            {"key": "C", "text": "核糖体"},
            {"key": "D", "text": "高尔基体"},
        ],
        "answer": {"keys": ["A"]},
    }
    assert choice_structure_valid(question)
    question["options"][3]["text"] = "线粒体"
    assert not choice_structure_valid(question)


def test_constructed_question_requires_matching_subparts_and_rubric():
    question = {
        "type": "proof",
        "content": "证明命题。",
        "answer": {"subparts": [{"id": "p1", "expected_points": ["使用定义"]}]},
        "subparts": [
            {
                "id": "p1",
                "prompt": "给出证明。",
                "rubric": {
                    "max_score": 5,
                    "criteria": [{"description": "使用定义", "points": 5}],
                },
            }
        ],
        "source_span": {"quote": "定义如下。"},
    }
    assert answer_exists(question, "定义如下。")
    assert choice_structure_valid(question)
    assert rubric_valid(question["subparts"])
    question["subparts"][0]["rubric"]["criteria"][0]["points"] = 4
    assert not rubric_valid(question["subparts"])


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


@pytest.mark.asyncio
async def test_invalid_distractor_clears_choice_options(monkeypatch):
    question = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [
            {"key": "A", "text": "叶绿体"},
            {"key": "B", "text": "线粒体"},
            {"key": "C", "text": "核糖体"},
            {"key": "D", "text": "高尔基体"},
        ],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "source_span": {"quote": "光合作用发生在叶绿体中，线粒体进行呼吸作用。"},
        "explanation": "叶绿体是光合作用的场所。",
    }

    async def _judge(*_args, **_kwargs):
        return (
            '{"fluency":4,"accuracy":4,"complexity":3,"usability":4,'
            '"answer_exists":true,"unique_correct":true,"leak":false,'
            '"controversial":false,"guessable":false,"all_distractors_valid":false,'
            '"invalid_distractor_keys":["B"],"comment":"B 与正解等价"}'
        )

    monkeypatch.setattr("app.services.quality_gates.complete_json", _judge)
    out = await apply_gates(question, "光合作用发生在叶绿体中，线粒体进行呼吸作用。")

    assert out["options"] is None
    assert out["answer"] == {"texts": ["叶绿体"]}
    assert out["needs_review"] is True
    assert "invalid_distractor" in out["quality_scores"]["review_reasons"]


def test_bkt_increases_on_correct():
    p0 = 0.2
    p1 = update_mastery(p0, True)
    assert p1 > p0
    assert recommend_difficulty({"detail": 0.2}, "detail") == "easy"
    assert recommend_difficulty({"detail": 0.85}, "detail") == "hard"

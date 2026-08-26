import pytest

from app.services.distractor_engine import build_choice_question, filter_candidates


def test_filter_drops_near_duplicate_of_answer():
    cands = [
        {"text": "叶绿体"},
        {"text": "线粒体"},
        {"text": "核糖体"},
        {"text": "高尔基体"},
    ]
    kept = filter_candidates(
        cands,
        answer="叶绿体",
        stem="光合作用主要发生在？",
        passage="光合作用发生在叶绿体中。线粒体进行呼吸作用。核糖体合成蛋白质。",
    )
    texts = [c["text"] for c in kept]
    assert "叶绿体" not in texts
    assert len(texts) >= 2


def test_filter_drops_off_topic():
    kept = filter_candidates(
        [{"text": "完全无关的宇宙飞船编号XYZ"}],
        answer="叶绿体",
        stem="光合作用",
        passage="光合作用发生在叶绿体中",
    )
    assert kept == [] or all("叶绿体" not in c["text"] for c in kept)


@pytest.mark.asyncio
async def test_true_false_options_are_dui_cuo():
    q = await build_choice_question(
        {
            "stem": "线粒体是光合作用的主要场所。",
            "type": "true_false",
            "answer": {"keys": ["false"]},
            "correct_text": "false",
            "explanation": "线粒体负责呼吸作用",
            "knowledge_tags": ["细胞器"],
            "micro_skill": "inference",
            "difficulty": "easy",
            "cognitive_level": "understand",
            "source_quote": "线粒体负责有氧呼吸",
        },
        "线粒体负责有氧呼吸。叶绿体进行光合作用。",
        "c1",
    )
    assert q["options"] == [{"key": "对", "text": "对"}, {"key": "错", "text": "错"}]
    assert q["answer"]["keys"] == ["错"]
    packed = await build_choice_question(
        {
            "stem": "叶绿体进行光合作用。",
            "type": "true_false",
            "answer": {"keys": ["对"]},
            "correct_text": "对",
            "explanation": "原文",
            "knowledge_tags": [],
            "micro_skill": "gist",
            "difficulty": "easy",
            "cognitive_level": "understand",
            "source_quote": "叶绿体进行光合作用",
        },
        "叶绿体进行光合作用。",
        "c2",
    )
    assert packed["answer"]["keys"] == ["对"]
    assert packed["options"] == [{"key": "对", "text": "对"}, {"key": "错", "text": "错"}]

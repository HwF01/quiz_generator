import pytest

from app.services.distractor_engine import (
    adversarial_fix,
    build_choice_question,
    filter_candidates,
    validate_candidates,
)


async def test_filter_drops_near_duplicate_of_answer():
    cands = [
        {"text": "叶绿体"},
        {"text": "线粒体"},
        {"text": "核糖体"},
        {"text": "高尔基体"},
    ]
    kept = await filter_candidates(
        cands,
        answer="叶绿体",
        stem="光合作用主要发生在？",
        passage="光合作用发生在叶绿体中。线粒体进行呼吸作用。核糖体合成蛋白质。",
    )
    texts = [c["text"] for c in kept]
    assert "叶绿体" not in texts
    assert len(texts) >= 2


async def test_filter_drops_off_topic():
    kept = await filter_candidates(
        [{"text": "完全无关的宇宙飞船编号XYZ"}],
        answer="叶绿体",
        stem="光合作用",
        passage="光合作用发生在叶绿体中",
    )
    assert kept == [] or all("叶绿体" not in c["text"] for c in kept)


async def test_filter_drops_near_duplicate_of_any_correct():
    kept = await filter_candidates(
        [
            {"text": "线粒体"},
            {"text": "核糖体"},
            {"text": "高尔基体"},
        ],
        answer=["叶绿体", "线粒体"],
        stem="下列哪些是细胞器？",
        passage="叶绿体进行光合作用。线粒体进行呼吸作用。核糖体合成蛋白质。",
    )
    texts = [c["text"] for c in kept]
    assert "线粒体" not in texts
    assert "叶绿体" not in texts
    assert len(texts) >= 1


async def test_filter_dashscope_drops_answer_near_dup_and_offtopic(monkeypatch):
    import numpy as np

    from app.services.llm.embed import DASHSCOPE_BACKEND

    def unit(*xs: float) -> np.ndarray:
        arr = np.array(xs, dtype=np.float32)
        return arr / np.linalg.norm(arr)

    catalog = {
        "叶绿体": unit(1.0, 0.0),
        "叶绿体中": unit(0.99, 0.14),
        "线粒体": unit(0.55, 0.84),
        "完全无关的宇宙飞船编号XYZ": unit(-0.8, 0.2),
        "context": unit(0.6, 0.8),
    }

    async def fake_embed(texts: list[str]):
        out = []
        for text in texts:
            if text in catalog:
                out.append(catalog[text])
            else:
                out.append(catalog["context"])
        return out, DASHSCOPE_BACKEND

    monkeypatch.setattr("app.services.distractor_engine.embed_texts", fake_embed)
    kept = await filter_candidates(
        [
            {"text": "叶绿体中"},
            {"text": "线粒体"},
            {"text": "完全无关的宇宙飞船编号XYZ"},
        ],
        answer="叶绿体",
        stem="光合作用主要发生在？",
        passage="光合作用发生在叶绿体中。线粒体进行呼吸作用。",
    )
    texts = [c["text"] for c in kept]
    assert texts == ["线粒体"]


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


@pytest.mark.asyncio
async def test_insufficient_candidates_create_review_draft_without_placeholder(monkeypatch):
    async def _overgenerate(*_args, **_kwargs):
        return [{"text": "线粒体", "error_type": "张冠李戴"}]

    async def _validate(candidates, **_kwargs):
        return candidates, False

    monkeypatch.setattr("app.services.distractor_engine.overgenerate", _overgenerate)
    monkeypatch.setattr("app.services.distractor_engine.validate_candidates", _validate)
    question = await build_choice_question(
        {
            "stem": "光合作用主要发生在哪里？",
            "type": "single_choice",
            "correct_text": "叶绿体",
            "answer": {"texts": ["叶绿体"]},
            "explanation": "叶绿体是光合作用的场所。",
            "source_quote": "光合作用发生在叶绿体中，线粒体进行呼吸作用。",
        },
        "光合作用发生在叶绿体中，线粒体进行呼吸作用。",
        "c1",
    )

    assert question["options"] is None
    assert question["needs_review"] is True
    assert "distractors_insufficient" in question["quality_scores"]["review_reasons"]


@pytest.mark.asyncio
async def test_multi_choice_packs_two_correct_keys(monkeypatch):
    async def _overgenerate(*_args, **_kwargs):
        return [
            {"text": "核糖体", "error_type": "张冠李戴", "rationale": "合成蛋白质"},
            {"text": "高尔基体", "error_type": "同维混淆", "rationale": "加工蛋白质"},
            {"text": "液泡", "error_type": "范围偏移", "rationale": "储藏物质"},
        ]

    async def _passthrough(candidates, **_kwargs):
        return candidates

    async def _validate(candidates, **_kwargs):
        return candidates, False

    async def _identity(question, _passage):
        return question

    monkeypatch.setattr("app.services.distractor_engine.overgenerate", _overgenerate)
    monkeypatch.setattr("app.services.distractor_engine.filter_candidates", _passthrough)
    monkeypatch.setattr("app.services.distractor_engine.validate_candidates", _validate)
    monkeypatch.setattr("app.services.distractor_engine.adversarial_fix", _identity)
    question = await build_choice_question(
        {
            "stem": "下列哪些是细胞器？",
            "type": "multi_choice",
            "correct_texts": ["叶绿体", "线粒体"],
            "correct_text": "叶绿体",
            "explanation": "二者都是细胞器。",
            "source_quote": "叶绿体进行光合作用，线粒体进行呼吸作用。",
        },
        "叶绿体进行光合作用，线粒体进行呼吸作用。核糖体合成蛋白质。",
        "c1",
    )

    assert question["options"] is not None
    assert len(question["options"]) == 4
    assert len(question["answer"]["keys"]) == 2
    texts = {opt["text"] for opt in question["options"]}
    assert {"叶绿体", "线粒体"} <= texts
    correct_texts = {
        opt["text"]
        for opt in question["options"]
        if opt["key"] in question["answer"]["keys"]
    }
    assert correct_texts == {"叶绿体", "线粒体"}


@pytest.mark.asyncio
async def test_multi_choice_insufficient_distractors_create_review_draft(monkeypatch):
    async def _overgenerate(*_args, **_kwargs):
        return [{"text": "核糖体", "error_type": "张冠李戴"}]

    async def _passthrough(candidates, **_kwargs):
        return candidates

    async def _validate(candidates, **_kwargs):
        return candidates, False

    monkeypatch.setattr("app.services.distractor_engine.overgenerate", _overgenerate)
    monkeypatch.setattr("app.services.distractor_engine.filter_candidates", _passthrough)
    monkeypatch.setattr("app.services.distractor_engine.validate_candidates", _validate)
    question = await build_choice_question(
        {
            "stem": "下列哪些是细胞器？",
            "type": "multi_choice",
            "correct_texts": ["叶绿体", "线粒体"],
            "explanation": "二者都是细胞器。",
            "source_quote": "叶绿体进行光合作用，线粒体进行呼吸作用。",
        },
        "叶绿体进行光合作用，线粒体进行呼吸作用。",
        "c1",
    )

    assert question["options"] is None
    assert question["needs_review"] is True
    assert "distractors_insufficient" in question["quality_scores"]["review_reasons"]
    assert question["answer"]["texts"] == ["叶绿体", "线粒体"]


@pytest.mark.asyncio
async def test_candidate_validator_rejects_semantic_equivalent(monkeypatch):
    async def _judge(*_args, **_kwargs):
        return (
            '{"results":[{"id":"0","verdict":"equivalent_to_answer","error_type":"同维混淆",'
            '"evidence_quote":"","reason":"与正解同义"}]}'
        )

    monkeypatch.setattr("app.services.distractor_engine.complete_json", _judge)
    accepted, critic_error = await validate_candidates(
        [{"text": "叶绿体中"}],
        stem="光合作用主要发生在哪里？",
        answer="叶绿体",
        passage="光合作用发生在叶绿体中。",
    )

    assert accepted == []
    assert critic_error is False


@pytest.mark.asyncio
async def test_adversarial_replacement_must_pass_candidate_validation(monkeypatch):
    async def _review(*_args, **_kwargs):
        return '{"too_easy_keys":["B"],"replacements":{"B":{"text":"叶绿体中","rationale":"同义"}},"guessable":false}'

    async def _reject(*_args, **_kwargs):
        return [], False

    monkeypatch.setattr("app.services.distractor_engine.complete_json", _review)
    monkeypatch.setattr("app.services.distractor_engine.validate_candidates", _reject)
    question = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [{"key": "A", "text": "叶绿体"}, {"key": "B", "text": "线粒体"}],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "quality_scores": {},
    }

    out = await adversarial_fix(question, "光合作用发生在叶绿体中，线粒体进行呼吸作用。")

    assert out["options"][1]["text"] == "线粒体"
    assert "adversarial_replacement_rejected" in out["quality_scores"]["review_reasons"]

import json

import pytest

from app.services.distractor_engine import build_choice_question, overgenerate
from app.services.jsonutil import parse_json


def _broken_overgenerate_json() -> str:
    """LLM-style JSON with unescaped quotes — same class as user error."""
    lines = ['{', '  "candidates": [']
    for i in range(10):
        lines.extend(
            [
                "    {",
                f'      "text": "候选{i}",',
                '      "error_type": "同维混淆",',
                '      "rationale": "易混",',
                '      "evidence_quote": "原文片段"',
                "    },",
            ]
        )
    lines.extend(
        [
            "    {",
            '      "text": "当误差小于 "1e-6" 时停止",',
            '      "error_type": "数值偏移",',
            '      "rationale": "阈值写错",',
            '      "evidence_quote": "误差阈值"',
            "    },",
            "    {",
            '      "text": "收敛阶为2",',
            '      "error_type": "部分正确",',
            '      "rationale": "阶次",',
            '      "evidence_quote": "阶"',
            "    }",
            "  ]",
            "}",
        ]
    )
    return "\n".join(lines)


def test_broken_llm_json_matches_user_symptom():
    bad = _broken_overgenerate_json()
    with pytest.raises(json.JSONDecodeError, match="Expecting ',' delimiter"):
        json.loads(bad)


@pytest.mark.asyncio
async def test_overgenerate_tolerates_malformed_llm_json(monkeypatch):
    async def _broken(*_args, **_kwargs):
        return _broken_overgenerate_json()

    monkeypatch.setattr("app.services.distractor_engine.complete_json", _broken)
    assert await overgenerate("题干", "正解", "材料段落") == []


@pytest.mark.asyncio
async def test_build_choice_survives_malformed_overgenerate_json(monkeypatch):
    async def _broken(*_args, **_kwargs):
        return _broken_overgenerate_json()

    monkeypatch.setattr("app.services.distractor_engine.complete_json", _broken)
    question = await build_choice_question(
        {
            "stem": "数值方法中常用的收敛判据是？",
            "type": "single_choice",
            "correct_text": "相对误差小于给定阈值",
            "answer": {"texts": ["相对误差小于给定阈值"]},
            "explanation": "材料给出误差阈值判据。",
            "source_quote": "当相对误差小于给定阈值时停止迭代。",
        },
        "当相对误差小于给定阈值时停止迭代。牛顿法局部收敛阶约为2。",
        "c-eng",
    )
    assert question["needs_review"] is True
    assert question["options"] is None
    assert "distractors_insufficient" in question["quality_scores"]["review_reasons"]


def test_parse_json_strips_trailing_commas():
    data = parse_json('{"candidates":[{"text":"a",},],}')
    assert data == {"candidates": [{"text": "a"}]}

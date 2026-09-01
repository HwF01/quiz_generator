from app.services.llm.providers import _mock_json
from app.services.quiz_generator import valid_stem_payload


def _tf_payload(stem: str, keys: list[str] | None = None) -> dict:
    return {
        "stem": stem,
        "type": "true_false",
        "explanation": "线粒体负责呼吸作用。",
        "source_quote": "线粒体负责有氧呼吸。",
        "correct_text": (keys or ["错"])[0],
        "answer": {"keys": keys or ["错"]},
    }


def test_valid_stem_payload_true_false_accepts_statement():
    passage = "线粒体负责有氧呼吸。叶绿体进行光合作用。"
    assert valid_stem_payload(
        _tf_payload("线粒体是植物细胞进行光合作用的主要场所。"),
        passage,
    )
    assert valid_stem_payload(
        _tf_payload("材料表明：叶绿体进行光合作用。", ["对"]),
        passage,
    )


def test_valid_stem_payload_true_false_rejects_question_stems():
    passage = "线粒体负责有氧呼吸。叶绿体进行光合作用。"
    assert not valid_stem_payload(_tf_payload("线粒体是光合作用的主要场所吗？"), passage)
    assert not valid_stem_payload(_tf_payload("根据材料，下列说法正确的是？"), passage)
    assert not valid_stem_payload(_tf_payload("下列关于线粒体的说法是否正确"), passage)


def test_mock_stem_true_false_is_statement():
    blob = (
        "不要输出干扰项\n题型：true_false\n"
        "【待考查文本开始】\n光合作用是绿色植物利用光能的过程。\n【待考查文本结束】\n"
    )
    data = _mock_json(blob)
    assert data["type"] == "true_false"
    stem = str(data.get("stem") or "")
    assert stem
    assert "？" not in stem and "?" not in stem
    assert valid_stem_payload(data, "光合作用是绿色植物利用光能的过程。")

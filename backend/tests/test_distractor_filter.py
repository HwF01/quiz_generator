from app.services.distractor_engine import filter_candidates


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

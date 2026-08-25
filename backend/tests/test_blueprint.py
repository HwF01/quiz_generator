from app.services.blueprint import allocate, enforce_detail_cap
from app.schemas.quiz import QuizBlueprint


def test_allocate_respects_detail_cap():
    bp = QuizBlueprint(total_questions=10, max_detail_ratio=0.3)
    allocs = allocate(12, bp)
    assert len(allocs) == 10
    details = [a for a in allocs if a["micro_skill"] == "detail"]
    assert len(details) <= 3


def test_enforce_detail_cap_drops_low_usability():
    qs = [
        {"micro_skill": "detail", "quality_scores": {"usability": 2}},
        {"micro_skill": "detail", "quality_scores": {"usability": 5}},
        {"micro_skill": "detail", "quality_scores": {"usability": 4}},
        {"micro_skill": "inference", "quality_scores": {"usability": 4}},
    ]
    out = enforce_detail_cap(qs, 0.3)
    details = [q for q in out if q["micro_skill"] == "detail"]
    assert len(details) <= 1
    assert details[0]["quality_scores"]["usability"] == 5

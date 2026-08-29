import pytest

from app.services.blueprint import allocate, allowed_question_types, enforce_detail_cap
from app.schemas.quiz import QuizBlueprint


def test_allocate_respects_detail_cap():
    bp = QuizBlueprint(total_questions=10, max_detail_ratio=0.3)
    allocs = allocate(12, bp)
    assert len(allocs) == 10
    details = [a for a in allocs if a["micro_skill"] == "detail"]
    assert len(details) <= 3


def test_allocate_only_choice_and_true_false():
    bp = QuizBlueprint(total_questions=10, type_mix={"single_choice": 0.7, "true_false": 0.2, "fill_blank": 0.1})
    allocs = allocate(10, bp)
    assert {a["type"] for a in allocs} <= {"single_choice", "true_false"}
    assert "fill_blank" not in {a["type"] for a in allocs}


def test_allocate_keeps_quality_first_count_when_items_are_few():
    bp = QuizBlueprint(total_questions=8)
    allocs = allocate(6, bp)
    assert len(allocs) == 6


def test_manual_allocation_keeps_integer_counts_for_supported_subject():
    bp = QuizBlueprint(
        total_questions=5,
        allocation_mode="manual",
        type_counts={"single_choice": 1, "fill_blank": 2, "application": 2},
    )
    allocs = allocate(5, bp, subject_tags=["engineering"])
    assert [item["type"] for item in allocs].count("fill_blank") == 2
    assert [item["type"] for item in allocs].count("application") == 2


def test_manual_allocation_rejects_type_outside_subject_matrix():
    bp = QuizBlueprint(
        total_questions=2,
        allocation_mode="manual",
        type_counts={"proof": 2},
    )
    with pytest.raises(ValueError, match="当前学科不支持题型"):
        allocate(2, bp, subject_tags=["logic"])


def test_auto_allocation_uses_subject_matrix_and_target_difficulty():
    bp = QuizBlueprint(total_questions=6, target_difficulty="hard")
    allocs = allocate(6, bp, subject_tags=["science", "math"], suggested_types=["proof", "proof"])
    assert len(allocs) == 6
    assert "proof" in {item["type"] for item in allocs}
    assert {item["difficulty"] for item in allocs} == {"hard"}
    assert allowed_question_types(["humanities"]) == [
        "single_choice",
        "true_false",
        "fill_blank",
        "short_answer",
    ]


def test_enforce_detail_cap_drops_low_usability():
    qs = [
        {"micro_skill": "detail", "quality_scores": {"usability": 2}},
        {"micro_skill": "detail", "quality_scores": {"usability": 5}},
        {"micro_skill": "detail", "quality_scores": {"usability": 4}},
        {"micro_skill": "inference", "quality_scores": {"usability": 4}},
    ]
    out = enforce_detail_cap(qs, 0.3)
    details = [q for q in out if q["micro_skill"] == "detail"]
    assert len(out) == 4
    assert len(details) <= 1
    assert details[0]["quality_scores"]["usability"] == 5

from __future__ import annotations

import json

from app.core.exceptions import AppError
from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt

CONSTRUCTED_TYPES = frozenset({"fill_blank", "application", "proof", "short_answer"})


def is_constructed(question: dict) -> bool:
    return question.get("type") in CONSTRUCTED_TYPES


def rubric_valid(subparts: object) -> bool:
    if not isinstance(subparts, list) or not subparts:
        return False
    for part in subparts:
        if not isinstance(part, dict) or not part.get("id") or not part.get("prompt"):
            return False
        rubric = part.get("rubric")
        if not isinstance(rubric, dict):
            return False
        max_score = rubric.get("max_score")
        criteria = rubric.get("criteria")
        if not isinstance(max_score, int) or isinstance(max_score, bool) or max_score < 1:
            return False
        if not isinstance(criteria, list) or not criteria:
            return False
        if any(
            not isinstance(item, dict)
            or not str(item.get("description") or "").strip()
            or not isinstance(item.get("points"), int)
            or isinstance(item.get("points"), bool)
            or item["points"] < 1
            for item in criteria
        ):
            return False
        if sum(item["points"] for item in criteria) != max_score:
            return False
    return True


async def build_grading_rubric(
    question: dict, passage: str, *, subject: str = "general"
) -> dict:
    if not is_constructed(question):
        return question
    provider = critic_provider(subject)
    prompt = load_prompt("build_grading_rubric")
    user = (
        f"题型：{question.get('type')}\n题干：{question.get('content')}\n"
        f"小问：{json.dumps(question.get('subparts') or [], ensure_ascii=False)}\n"
        f"正解：{json.dumps(question.get('answer') or {}, ensure_ascii=False)}\n"
        f"外部参考资料：{json.dumps(question.get('external_sources') or [], ensure_ascii=False)}\n"
        f"【待考查文本开始】\n{passage[:1800]}\n【待考查文本结束】"
    )
    try:
        data = parse_json(await complete_json(provider, prompt, user, temperature=0.2))
    except Exception:
        return _mark_rubric_review(question, "rubric_critic_error")
    rubrics = data.get("rubrics") if isinstance(data, dict) else None
    by_id = {
        str(rubric.get("id")): rubric
        for rubric in rubrics or []
        if isinstance(rubric, dict) and rubric.get("id")
    }
    enriched = []
    for part in question.get("subparts") or []:
        part_id = str(part.get("id") or "")
        rubric = by_id.get(part_id)
        if not rubric:
            return _mark_rubric_review(question, "invalid_grading_rubric")
        enriched.append({**part, "rubric": _clean_rubric(rubric)})
    question["subparts"] = enriched
    if not data.get("valid", False) or not rubric_valid(enriched):
        return _mark_rubric_review(question, "invalid_grading_rubric")
    return question


async def grade_constructed_response(
    question: dict, user_answer: dict[str, str], *, subject: str = "general"
) -> dict:
    if not is_constructed(question) or not rubric_valid(question.get("subparts")):
        raise AppError("该题尚未具备可用评分量规，请先审校题目", code=400)
    provider = critic_provider(subject)
    prompt = load_prompt("grade_constructed_response")
    user = (
        f"题型：{question.get('type')}\n题干：{question.get('content')}\n"
        f"小问与量规：{json.dumps(question.get('subparts') or [], ensure_ascii=False)}\n"
        f"正解：{json.dumps(question.get('answer') or {}, ensure_ascii=False)}\n"
        f"学习者作答：{json.dumps(user_answer, ensure_ascii=False)}\n"
        f"外部参考资料：{json.dumps(question.get('external_sources') or [], ensure_ascii=False)}"
    )
    try:
        data = parse_json(await complete_json(provider, prompt, user, temperature=0.1))
    except Exception as exc:
        raise AppError("AI 批改暂不可用，请稍后重试", code=503, status_code=503) from exc
    if not isinstance(data, dict) or data.get("status") == "needs_review":
        return {
            "status": "needs_review",
            "message": str((data or {}).get("message") or "AI 无法可靠判断，请人工复核"),
            "provider": getattr(provider, "name", "critic"),
            "model": getattr(provider, "model", ""),
        }
    parts = _validated_grade_parts(data.get("subparts"), question.get("subparts") or [])
    if parts is None:
        raise AppError("AI 批改结果格式无效，请稍后重试", code=503, status_code=503)
    score = sum(part["score"] for part in parts)
    max_score = sum(part["max_score"] for part in parts)
    return {
        "status": "graded",
        "subparts": parts,
        "score": score,
        "max_score": max_score,
        "percent": round(100 * score / max_score, 1),
        "overall_feedback": str(data.get("overall_feedback") or ""),
        "provider": getattr(provider, "name", "critic"),
        "model": getattr(provider, "model", ""),
    }


def normalize_answer(question: dict, answer: object) -> dict[str, str]:
    subparts = question.get("subparts") or []
    if isinstance(answer, dict):
        return {
            str(part.get("id")): str(answer.get(str(part.get("id"))) or "").strip()
            for part in subparts
        }
    if len(subparts) == 1:
        return {str(subparts[0].get("id")): str(answer or "").strip()}
    return {str(part.get("id")): "" for part in subparts}


def _clean_rubric(rubric: dict) -> dict:
    criteria = [
        {"description": str(item.get("description") or "").strip(), "points": item.get("points")}
        for item in rubric.get("criteria") or []
        if isinstance(item, dict)
    ]
    return {"max_score": rubric.get("max_score"), "criteria": criteria}


def _validated_grade_parts(raw_parts: object, subparts: list[dict]) -> list[dict] | None:
    if not isinstance(raw_parts, list):
        return None
    raw_by_id = {
        str(item.get("id")): item
        for item in raw_parts
        if isinstance(item, dict) and item.get("id") is not None
    }
    if len(raw_by_id) != len(subparts):
        return None
    validated = []
    for part in subparts:
        part_id = str(part.get("id"))
        result = raw_by_id.get(part_id)
        rubric = part.get("rubric") or {}
        max_score = rubric.get("max_score")
        score = result.get("score") if result else None
        if (
            not isinstance(score, int)
            or isinstance(score, bool)
            or not isinstance(max_score, int)
            or score < 0
            or score > max_score
        ):
            return None
        validated.append(
            {
                "id": part_id,
                "score": score,
                "max_score": max_score,
                "evidence": str(result.get("evidence") or "").strip(),
                "feedback": str(result.get("feedback") or "").strip(),
            }
        )
    return validated


def _mark_rubric_review(question: dict, reason: str) -> dict:
    scores = question.get("quality_scores") or {}
    reasons = list(scores.get("review_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    scores["review_reasons"] = reasons
    question["quality_scores"] = scores
    question["needs_review"] = True
    return question

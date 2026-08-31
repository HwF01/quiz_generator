from __future__ import annotations

import re

from app.services.jsonutil import parse_json
from app.services.blueprint import allowed_question_types
from app.services.llm.embed import similarity
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt
from app.services.subjective_grading import is_constructed, rubric_valid


def _normalized(text: object) -> str:
    return re.sub(r"[\s，。；、：“”‘’（）()【】\[\]「」]+", "", str(text or "")).lower()


def answer_exists(question: dict, passage: str = "") -> bool:
    span = question.get("source_span") or {}
    quote = str(span.get("quote") or "")
    if not quote:
        return False
    if passage and _normalized(quote) not in _normalized(passage):
        return False
    answer = question.get("answer") or {}
    if is_constructed(question):
        answer_parts = answer.get("subparts") or []
        if not isinstance(answer_parts, list) or not answer_parts:
            return False
        for part in answer_parts:
            if not isinstance(part, dict) or not part.get("id"):
                return False
            values = part.get("texts") if question.get("type") == "fill_blank" else part.get("expected_points")
            if not [value for value in values or [] if str(value).strip()]:
                return False
        return True
    texts = answer.get("texts") or []
    keys = answer.get("keys") or []
    if question.get("type") == "true_false":
        return True
    hay = quote
    for t in texts:
        if t and (t in hay or similarity(str(t), quote) >= 0.35):
            return True
    if keys and question.get("options"):
        for opt in question["options"]:
            if opt.get("key") in keys and similarity(opt.get("text", ""), quote) >= 0.3:
                return True
    return False


def choice_structure_valid(question: dict) -> bool:
    question_type = question.get("type")
    if is_constructed(question):
        subparts = question.get("subparts")
        answers = (question.get("answer") or {}).get("subparts")
        if not isinstance(subparts, list) or not isinstance(answers, list) or not subparts:
            return False
        part_ids = {str(part.get("id") or "") for part in subparts if isinstance(part, dict)}
        answer_ids = {str(part.get("id") or "") for part in answers if isinstance(part, dict)}
        return bool(part_ids) and len(part_ids) == len(subparts) and part_ids == answer_ids
    if question_type not in {"single_choice", "multi_choice", "true_false"}:
        return True
    options = question.get("options") or []
    keys = (question.get("answer") or {}).get("keys") or []
    expected_options = 4 if question_type != "true_false" else 2
    min_keys, max_keys = (2, 3) if question_type == "multi_choice" else (1, 1)
    if len(options) != expected_options or not (min_keys <= len(keys) <= max_keys):
        return False
    if any(not isinstance(option, dict) for option in options):
        return False
    option_keys = [str(option.get("key") or "") for option in options]
    option_texts = [_normalized(option.get("text")) for option in options]
    key_values = [str(key) for key in keys]
    return (
        all(option_keys)
        and all(option_texts)
        and len(set(option_keys)) == expected_options
        and len(set(option_texts)) == expected_options
        and len(set(key_values)) == len(key_values)
        and all(key in option_keys for key in key_values)
    )


def is_practice_eligible(question: dict) -> bool:
    return (not question.get("needs_review")) and choice_structure_valid(question)


def unique_correct(question: dict) -> bool:
    options = question.get("options") or []
    answer = question.get("answer") or {}
    keys = set(answer.get("keys") or [])
    if is_constructed(question) or question.get("type") == "true_false":
        return True
    correct = [o for o in options if o.get("key") in keys]
    wrong = [o for o in options if o.get("key") not in keys]
    if not correct or len(correct) != len(keys):
        return False
    for citem in correct:
        ctext = citem.get("text") or ""
        for w in wrong:
            if similarity(ctext, w.get("text") or "") >= 0.88:
                return False
    return True


def stem_leaks_answer(question: dict) -> bool:
    stem = question.get("content") or ""
    answer = question.get("answer") or {}
    texts = [str(t) for t in (answer.get("texts") or []) if t]
    if question.get("type") not in {"single_choice", "multi_choice"}:
        return False
    for t in texts:
        if len(t) >= 2 and t in stem:
            return True
    return False


async def judge_with_critic(question: dict, passage: str) -> dict:
    provider = critic_provider()
    prompt = load_prompt("quality_judge")
    user = (
        f"题型：{question.get('type')}\n目标难度：{question.get('target_difficulty')}\n"
        f"题目：{question.get('content')}\n小问：{question.get('subparts')}\n选项：{question.get('options')}\n"
        f"答案：{question.get('answer')}\nsource_span：{question.get('source_span')}\n"
        f"外部来源：{question.get('external_sources')}\n"
        f"【待考查文本开始】\n{passage[:1800]}\n【待考查文本结束】"
    )
    try:
        raw = await complete_json(provider, prompt, user, temperature=0.2)
        return parse_json(raw)
    except Exception:
        return {
            "fluency": 0,
            "accuracy": 0,
            "complexity": 0,
            "usability": 0,
            "critic_error": True,
            "answer_exists": False,
            "unique_correct": False,
            "leak": False,
            "controversial": False,
            "guessable": False,
        }


async def apply_gates(
    question: dict, passage: str, *, subject_tags: list[str] | None = None
) -> dict:
    existing_scores = question.get("quality_scores") or {}
    existing_reasons = list(existing_scores.get("review_reasons") or [])
    exists = answer_exists(question, passage)
    structure = choice_structure_valid(question)
    unique = unique_correct(question)
    leak = stem_leaks_answer(question)
    rubric_ok = not is_constructed(question) or rubric_valid(question.get("subparts"))
    subject_ok = not subject_tags or question.get("type") in allowed_question_types(subject_tags)
    scores = await judge_with_critic(question, passage)
    critic_error = bool(scores.get("critic_error")) or "critic_error" in existing_reasons
    usability = int((scores.get("usability") or 0) if critic_error else (scores.get("usability") or 3))
    if scores.get("answer_exists") is False:
        exists = False
    check_distractors = question.get("type") in {"single_choice", "multi_choice"}
    invalid_distractor_keys = [
        str(key)
        for key in (scores.get("invalid_distractor_keys") or [])
        if key and check_distractors
    ]
    distractors_valid = (
        bool(scores.get("all_distractors_valid", not invalid_distractor_keys))
        if check_distractors
        else True
    )
    reasons = existing_reasons
    if not structure:
        reasons.append("invalid_choice_structure")
    if not exists:
        reasons.append("answer_not_in_source")
    if not unique:
        reasons.append("non_unique_correct")
    if leak:
        reasons.append("stem_leak")
    if not rubric_ok:
        reasons.append("invalid_grading_rubric")
    if not subject_ok:
        reasons.append("unsupported_question_type")
    if usability < 3:
        reasons.append("low_usability")
    if int(scores.get("accuracy") or 0) < 4:
        reasons.append("low_accuracy")
    if scores.get("controversial"):
        reasons.append("controversial")
    if scores.get("guessable"):
        reasons.append("guessable")
    if scores.get("difficulty_match") is False:
        reasons.append("difficulty_mismatch")
    if invalid_distractor_keys or not distractors_valid:
        reasons.append("invalid_distractor")
    if critic_error:
        reasons.append("critic_error")
    reasons = list(dict.fromkeys(reasons))
    needs = (
        (not exists)
        or (not structure)
        or (not unique)
        or leak
        or not rubric_ok
        or not subject_ok
        or usability < 3
        or int(scores.get("accuracy") or 0) < 4
        or scores.get("controversial")
        or scores.get("guessable")
        or scores.get("difficulty_match") is False
        or invalid_distractor_keys
        or not distractors_valid
        or critic_error
    )
    question["quality_scores"] = {
        "fluency": scores.get("fluency", 0 if critic_error else 3),
        "accuracy": scores.get("accuracy", 0 if critic_error else 3),
        "complexity": scores.get("complexity", 0 if critic_error else 3),
        "usability": usability,
        "answer_exists": exists,
        "unique_correct": unique,
        "leak": leak,
        "difficulty_match": scores.get("difficulty_match", True),
        "rubric_valid": rubric_ok,
        "subject_type_valid": subject_ok,
        "controversial": bool(scores.get("controversial")),
        "guessable": bool(scores.get("guessable")),
        "critic_error": critic_error,
        "comment": scores.get("comment"),
        "invalid_distractor_keys": invalid_distractor_keys,
        "all_distractors_valid": distractors_valid,
        "review_reasons": reasons,
    }
    question["needs_review"] = bool(needs or question.get("needs_review"))
    return question

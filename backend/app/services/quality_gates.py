from __future__ import annotations

import re

from app.services.jsonutil import parse_json
from app.services.llm.embed import similarity
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt


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
    if question.get("type") != "single_choice":
        return True
    options = question.get("options") or []
    keys = (question.get("answer") or {}).get("keys") or []
    if len(options) != 4 or len(keys) != 1:
        return False
    if any(not isinstance(option, dict) for option in options):
        return False
    option_keys = [str(option.get("key") or "") for option in options]
    option_texts = [_normalized(option.get("text")) for option in options]
    return (
        all(option_keys)
        and all(option_texts)
        and len(set(option_keys)) == 4
        and len(set(option_texts)) == 4
        and keys[0] in option_keys
    )


def unique_correct(question: dict) -> bool:
    options = question.get("options") or []
    answer = question.get("answer") or {}
    keys = set(answer.get("keys") or [])
    if question.get("type") in {"fill_blank", "true_false"}:
        return True
    correct = [o for o in options if o.get("key") in keys]
    wrong = [o for o in options if o.get("key") not in keys]
    if not correct:
        return False
    ctext = correct[0].get("text") or ""
    for w in wrong:
        if similarity(ctext, w.get("text") or "") >= 0.88:
            return False
    return True


def stem_leaks_answer(question: dict) -> bool:
    stem = question.get("content") or ""
    answer = question.get("answer") or {}
    texts = [str(t) for t in (answer.get("texts") or []) if t]
    if question.get("type") == "fill_blank":
        return False
    for t in texts:
        if len(t) >= 2 and t in stem:
            return True
    return False


async def judge_with_critic(question: dict, passage: str) -> dict:
    provider = critic_provider()
    prompt = load_prompt("quality_judge")
    user = (
        f"题目：{question.get('content')}\n选项：{question.get('options')}\n"
        f"答案：{question.get('answer')}\nsource_span：{question.get('source_span')}\n"
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


async def apply_gates(question: dict, passage: str) -> dict:
    existing_scores = question.get("quality_scores") or {}
    existing_reasons = list(existing_scores.get("review_reasons") or [])
    exists = answer_exists(question, passage)
    structure = choice_structure_valid(question)
    unique = unique_correct(question)
    leak = stem_leaks_answer(question)
    scores = await judge_with_critic(question, passage)
    critic_error = bool(scores.get("critic_error")) or "critic_error" in existing_reasons
    usability = int((scores.get("usability") or 0) if critic_error else (scores.get("usability") or 3))
    if scores.get("answer_exists") is False:
        exists = False
    invalid_distractor_keys = [
        str(key) for key in (scores.get("invalid_distractor_keys") or []) if key
    ]
    distractors_valid = bool(scores.get("all_distractors_valid", not invalid_distractor_keys))
    reasons = existing_reasons
    if not structure:
        reasons.append("invalid_choice_structure")
    if not exists:
        reasons.append("answer_not_in_source")
    if not unique:
        reasons.append("non_unique_correct")
    if leak:
        reasons.append("stem_leak")
    if usability < 3:
        reasons.append("low_usability")
    if int(scores.get("accuracy") or 0) < 4:
        reasons.append("low_accuracy")
    if scores.get("controversial"):
        reasons.append("controversial")
    if scores.get("guessable"):
        reasons.append("guessable")
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
        or usability < 3
        or int(scores.get("accuracy") or 0) < 4
        or scores.get("controversial")
        or scores.get("guessable")
        or invalid_distractor_keys
        or not distractors_valid
        or critic_error
    )
    if question.get("type") == "single_choice" and (
        invalid_distractor_keys or not distractors_valid or critic_error
    ):
        answer = question.get("answer") or {}
        correct_keys = set(answer.get("keys") or [])
        correct_texts = [
            str(option.get("text") or "")
            for option in question.get("options") or []
            if option.get("key") in correct_keys
        ]
        question["options"] = None
        question["answer"] = {"texts": correct_texts or list(answer.get("texts") or [])}
    question["quality_scores"] = {
        "fluency": scores.get("fluency", 0 if critic_error else 3),
        "accuracy": scores.get("accuracy", 0 if critic_error else 3),
        "complexity": scores.get("complexity", 0 if critic_error else 3),
        "usability": usability,
        "answer_exists": exists,
        "unique_correct": unique,
        "leak": leak,
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

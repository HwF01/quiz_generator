from __future__ import annotations

from app.services.jsonutil import parse_json
from app.services.llm.embed import similarity
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt


def answer_exists(question: dict) -> bool:
    span = question.get("source_span") or {}
    quote = str(span.get("quote") or "")
    if not quote:
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
    exists = answer_exists(question)
    unique = unique_correct(question)
    leak = stem_leaks_answer(question)
    scores = await judge_with_critic(question, passage)
    critic_error = bool(scores.get("critic_error"))
    usability = int((scores.get("usability") or 0) if critic_error else (scores.get("usability") or 3))
    if scores.get("answer_exists") is False:
        exists = False
    needs = (
        (not exists)
        or (not unique)
        or leak
        or usability < 3
        or scores.get("controversial")
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
        "controversial": bool(scores.get("controversial")),
        "guessable": bool(scores.get("guessable")),
        "critic_error": critic_error,
        "comment": scores.get("comment"),
    }
    question["needs_review"] = bool(needs or question.get("needs_review"))
    return question

from __future__ import annotations

import asyncio
import json
import re

from app.services.llm.embed import similarity
from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt
from app.services.ranker import rank_candidates

ANSWER_SIM_TH = 0.86
PAIR_SIM_TH = 0.9
CONTEXT_SIM_TH = 0.12
TF_TRUE = {"true", "t", "1", "yes", "正确", "对"}
TF_FALSE = {"false", "f", "0", "no", "错误", "错"}
GENERIC_DISTRACTOR_RE = re.compile(
    r"相关但条件不同|同类的其他概念|另一处真实概念|前提条件|对立面|例外情况下|相关但错误",
    re.IGNORECASE,
)


def _normalized(text: object) -> str:
    return re.sub(r"[\s，。；、：“”‘’（）()【】\[\]「」]+", "", str(text or "")).lower()


def _add_review_reason(question: dict, reason: str) -> None:
    scores = question.get("quality_scores") or {}
    reasons = list(scores.get("review_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    scores["review_reasons"] = reasons
    question["quality_scores"] = scores
    question["needs_review"] = True


def is_tf_true(value: object) -> bool:
    token = str(value or "").strip().lower()
    if token in TF_FALSE:
        return False
    return token in TF_TRUE


def tf_option_label(option: dict) -> str:
    if is_tf_true(option.get("key")) or is_tf_true(option.get("text")):
        return "对"
    return "错"


def filter_candidates(
    candidates: list[dict],
    *,
    answer: str,
    stem: str,
    passage: str,
) -> list[dict]:
    kept: list[dict] = []
    for cand in candidates:
        text = str(cand.get("text") or "").strip()
        if not text or _normalized(text) == _normalized(answer):
            continue
        if GENERIC_DISTRACTOR_RE.search(text):
            continue
        # 仅作字面近似去重；同义性由 Critic 的候选验伪裁定。
        if similarity(text, answer) >= ANSWER_SIM_TH:
            continue
        if similarity(text, stem + "\n" + passage[:400]) < CONTEXT_SIM_TH:
            continue
        if any(similarity(text, str(k.get("text"))) >= PAIR_SIM_TH for k in kept):
            continue
        kept.append({**cand, "text": text})
    return kept


async def overgenerate(stem: str, answer: str, passage: str) -> list[dict]:
    provider = critic_provider()
    prompt = load_prompt("overgenerate_distractors")
    user = (
        f"题干：{stem}\n正确答案：{answer}\n"
        f"【待考查文本开始】\n{passage[:2500]}\n【待考查文本结束】"
    )
    try:
        raw = await complete_json(provider, prompt, user, temperature=0.7)
        data = parse_json(raw)
    except Exception:
        return []
    cands = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(cands, list):
        return []
    return [c for c in cands if isinstance(c, dict) and c.get("text")]


async def validate_candidates(
    candidates: list[dict],
    *,
    stem: str,
    answer: str,
    passage: str,
) -> tuple[list[dict], bool]:
    if not candidates:
        return [], False
    numbered = [{**cand, "id": str(i)} for i, cand in enumerate(candidates)]
    provider = critic_provider()
    prompt = load_prompt("validate_distractors")
    user = (
        f"题干：{stem}\n正确答案：{answer}\n候选：{json.dumps(numbered, ensure_ascii=False)}\n"
        f"【待考查文本开始】\n{passage[:2500]}\n【待考查文本结束】"
    )
    try:
        raw = await complete_json(provider, prompt, user, temperature=0.1)
        data = parse_json(raw)
    except Exception:
        return [], True
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return [], True
    verdicts = {
        str(result.get("id")): result
        for result in results
        if isinstance(result, dict) and result.get("id") is not None
    }
    accepted: list[dict] = []
    for candidate in numbered:
        result = verdicts.get(candidate["id"]) or {}
        if result.get("verdict") != "accepted":
            continue
        evidence = str(result.get("evidence_quote") or "").strip()
        if not evidence or _normalized(evidence) not in _normalized(passage):
            continue
        accepted.append(
            {
                **candidate,
                "rationale": str(result.get("reason") or candidate.get("rationale") or "材料相关的易错点"),
                "error_type": str(result.get("error_type") or candidate.get("error_type") or "同维混淆"),
                "evidence_quote": evidence,
            }
        )
    return accepted, False


async def adversarial_fix(question: dict, passage: str) -> dict:
    if not question.get("options"):
        return question
    provider = critic_provider()
    prompt = load_prompt("adversarial_review")
    user = (
        f"题目：{question.get('content')}\n选项：{question.get('options')}\n"
        f"答案：{question.get('answer')}\n【待考查文本开始】\n{passage[:1500]}\n【待考查文本结束】"
    )
    try:
        raw = await complete_json(provider, prompt, user, temperature=0.4)
        review = parse_json(raw)
    except Exception:
        _add_review_reason(question, "critic_error")
        return question
    options = list(question.get("options") or [])
    replacements = review.get("replacements") or {}
    candidates_by_key = {
        str(key): {**value, "text": str(value.get("text") or "").strip()}
        for key, value in replacements.items()
        if isinstance(value, dict) and str(value.get("text") or "").strip()
    }
    validated, critic_error = await validate_candidates(
        list(candidates_by_key.values()),
        stem=str(question.get("content") or ""),
        answer=str((question.get("answer") or {}).get("texts", [""])[0] or ""),
        passage=passage,
    )
    if critic_error:
        _add_review_reason(question, "critic_error")
        return question
    allowed = {_normalized(candidate["text"]): candidate for candidate in validated}
    for key in review.get("too_easy_keys") or []:
        repl = candidates_by_key.get(str(key))
        if not repl or _normalized(repl["text"]) not in allowed:
            _add_review_reason(question, "adversarial_replacement_rejected")
            continue
        for opt in options:
            if opt.get("key") == key:
                accepted = allowed[_normalized(repl["text"])]
                opt["text"] = accepted["text"]
                rationale = question.get("distractor_rationale") or {}
                rationale[key] = accepted.get("rationale") or rationale.get(key)
                question["distractor_rationale"] = rationale
    question["options"] = options
    if review.get("guessable"):
        _add_review_reason(question, "guessable")
    return question


async def build_choice_question(stem_payload: dict, passage: str, chunk_id: str) -> dict:
    stem = stem_payload.get("stem") or ""
    answer = stem_payload.get("correct_text") or ""
    qtype = stem_payload.get("type") or "single_choice"
    if qtype == "true_false":
        keys = stem_payload.get("answer", {}).get("keys") or ["对"]
        correct = is_tf_true(keys[0])
        options = [
            {"key": "对", "text": "对"},
            {"key": "错", "text": "错"},
        ]
        return _pack(
            stem_payload,
            options,
            {"keys": ["对" if correct else "错"]},
            {"错" if correct else "对": "与材料陈述相反或偷换条件"},
            chunk_id,
        )
    if qtype in {"fill_blank", "application", "proof", "short_answer"}:
        structured_answer = dict(stem_payload.get("answer") or {})
        if qtype == "fill_blank" and not structured_answer.get("texts"):
            structured_answer["texts"] = [
                text
                for part in structured_answer.get("subparts") or []
                for text in (part.get("texts") or [])
            ] or [answer]
        return _pack(stem_payload, None, structured_answer, None, chunk_id)

    cands = await overgenerate(stem, answer, passage)
    filtered = await asyncio.to_thread(
        filter_candidates, cands, answer=answer, stem=stem, passage=passage
    )
    validated, critic_error = await validate_candidates(
        filtered, stem=stem, answer=answer, passage=passage
    )
    if len(validated) < 3 and not critic_error:
        extra = await overgenerate(stem, answer, passage)
        filtered = await asyncio.to_thread(
            filter_candidates,
            filtered + extra,
            answer=answer,
            stem=stem,
            passage=passage,
        )
        validated, retry_critic_error = await validate_candidates(
            filtered, stem=stem, answer=answer, passage=passage
        )
        critic_error = retry_critic_error
    ranked = (
        await asyncio.to_thread(
            rank_candidates, validated, answer=answer, stem=stem, passage=passage
        )
    )[:3]
    if len(ranked) < 3:
        draft = _pack(
            stem_payload,
            None,
            {"texts": [answer]},
            None,
            chunk_id,
            needs_review=True,
        )
        _add_review_reason(
            draft, "critic_error" if critic_error else "distractors_insufficient"
        )
        return draft

    letters = ["A", "B", "C", "D"]
    options = [{"key": "A", "text": answer}]
    rationale = {}
    for i, cand in enumerate(ranked[:3]):
        key = letters[i + 1]
        options.append({"key": key, "text": cand["text"]})
        rationale[key] = cand.get("rationale") or cand.get("error_type") or "易错干扰"
    # rotate correct answer so it's not always A
    rotate = hash(stem) % 4
    options = options[rotate:] + options[:rotate]
    for i, opt in enumerate(options):
        opt["key"] = letters[i]
    correct_key = letters[(0 - rotate) % 4]
    remapped = {}
    # rationale keys were B C D before rotate; remap approximately by text
    text_to_reason = {c["text"]: c.get("rationale") for c in ranked}
    for opt in options:
        if opt["key"] != correct_key and opt["text"] in text_to_reason:
            remapped[opt["key"]] = text_to_reason[opt["text"]]
    packed = _pack(
        stem_payload,
        options,
        {"keys": [correct_key], "texts": [answer]},
        remapped,
        chunk_id,
    )
    packed = await adversarial_fix(packed, passage)
    return packed


def _pack(
    stem_payload,
    options,
    answer,
    rationale,
    chunk_id: str,
    *,
    needs_review: bool = False,
) -> dict:
    return {
        "type": stem_payload.get("type"),
        "content": stem_payload.get("stem"),
        "options": options,
        "answer": answer,
        "explanation": stem_payload.get("explanation"),
        "distractor_rationale": rationale,
        "difficulty": stem_payload.get("difficulty", "medium"),
        "knowledge_tags": stem_payload.get("knowledge_tags") or [],
        "micro_skill": stem_payload.get("micro_skill", "detail"),
        "cognitive_level": stem_payload.get("cognitive_level", "remember"),
        "subparts": stem_payload.get("subparts"),
        "source_span": {
            "chunk_id": chunk_id,
            "quote": stem_payload.get("source_quote") or "",
        },
        "external_source_ids": stem_payload.get("external_source_ids") or [],
        "target_difficulty": stem_payload.get("target_difficulty"),
        "source_chunk_id": chunk_id,
        "needs_review": bool(needs_review or stem_payload.get("needs_review")),
        "quality_scores": {},
    }

from __future__ import annotations

import json
import re

from app.services.llm.embed import cosine, embed_texts, thresholds_for
from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, critic_provider
from app.services.prompt_loader import load_prompt
from app.services.ranker import answer_texts, rank_candidates

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


def _answer_prompt(answer: str | list[str]) -> str:
    texts = answer_texts(answer)
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return json.dumps(texts, ensure_ascii=False)


def _correct_texts_from_stem(stem_payload: dict) -> list[str]:
    qtype = str(stem_payload.get("type") or "single_choice")
    if qtype == "multi_choice":
        raw = stem_payload.get("correct_texts")
        texts = answer_texts([str(item) for item in raw]) if isinstance(raw, list) else []
        return texts[:3]
    return answer_texts(str(stem_payload.get("correct_text") or ""))[:1]


async def filter_candidates(
    candidates: list[dict],
    *,
    answer: str | list[str],
    stem: str,
    passage: str,
) -> list[dict]:
    answers = answer_texts(answer)
    answer_norms = {_normalized(item) for item in answers}
    prepared: list[dict] = []
    for cand in candidates:
        text = str(cand.get("text") or "").strip()
        if not text or _normalized(text) in answer_norms:
            continue
        if GENERIC_DISTRACTOR_RE.search(text):
            continue
        prepared.append({**cand, "text": text})
    if not prepared:
        return []
    context = f"{stem}\n{passage[:400]}"
    vectors, backend = await embed_texts(
        [*answers, context, *[item["text"] for item in prepared]]
    )
    th = thresholds_for(backend)
    n_answers = len(answers)
    answer_vecs = vectors[:n_answers]
    context_vec = vectors[n_answers]
    kept: list[dict] = []
    kept_vecs: list[object] = []
    # 预过滤近重复与跑题；同义改写仍由 Critic 的候选验伪裁定。
    for cand, vec in zip(prepared, vectors[n_answers + 1 :]):
        if any(cosine(vec, answer_vec) >= th.answer_sim for answer_vec in answer_vecs):
            continue
        if cosine(vec, context_vec) < th.context_sim:
            continue
        if any(cosine(vec, other) >= th.pair_sim for other in kept_vecs):
            continue
        kept.append(cand)
        kept_vecs.append(vec)
    return kept


async def overgenerate(stem: str, answer: str | list[str], passage: str) -> list[dict]:
    provider = critic_provider()
    prompt = load_prompt("overgenerate_distractors")
    user = (
        f"题干：{stem}\n正确答案：{_answer_prompt(answer)}\n"
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
    answer: str | list[str],
    passage: str,
) -> tuple[list[dict], bool]:
    if not candidates:
        return [], False
    numbered = [{**cand, "id": str(i)} for i, cand in enumerate(candidates)]
    provider = critic_provider()
    prompt = load_prompt("validate_distractors")
    user = (
        f"题干：{stem}\n正确答案：{_answer_prompt(answer)}\n候选：{json.dumps(numbered, ensure_ascii=False)}\n"
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
        answer=_correct_texts_from_question(question),
        passage=passage,
    )
    if critic_error:
        _add_review_reason(question, "critic_error")
        return question
    allowed = {_normalized(candidate["text"]): candidate for candidate in validated}
    correct_keys = {str(key) for key in ((question.get("answer") or {}).get("keys") or [])}
    for key in review.get("too_easy_keys") or []:
        if str(key) in correct_keys:
            continue
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
    corrects = _correct_texts_from_stem(stem_payload)
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
            ] or corrects
        return _pack(stem_payload, None, structured_answer, None, chunk_id)

    needed = _distractor_needed(qtype, len(corrects))
    cands = await overgenerate(stem, corrects, passage)
    filtered = await filter_candidates(
        cands, answer=corrects, stem=stem, passage=passage
    )
    validated, critic_error = await validate_candidates(
        filtered, stem=stem, answer=corrects, passage=passage
    )
    if len(validated) < needed and not critic_error:
        extra = await overgenerate(stem, corrects, passage)
        filtered = await filter_candidates(
            filtered + extra,
            answer=corrects,
            stem=stem,
            passage=passage,
        )
        validated, retry_critic_error = await validate_candidates(
            filtered, stem=stem, answer=corrects, passage=passage
        )
        critic_error = retry_critic_error
    ranked = (
        await rank_candidates(validated, answer=corrects, stem=stem, passage=passage)
    )[:needed]
    if len(ranked) < needed or not corrects:
        draft = _pack(
            stem_payload,
            None,
            {"texts": corrects},
            None,
            chunk_id,
            needs_review=True,
        )
        _add_review_reason(
            draft, "critic_error" if critic_error else "distractors_insufficient"
        )
        return draft

    letters = ["A", "B", "C", "D"]
    options = [{"key": letters[i], "text": text} for i, text in enumerate(corrects)]
    rationale = {}
    for i, cand in enumerate(ranked[:needed]):
        key = letters[len(corrects) + i]
        options.append({"key": key, "text": cand["text"]})
        rationale[key] = cand.get("rationale") or cand.get("error_type") or "易错干扰"
    rotate = hash(stem) % 4
    options = options[rotate:] + options[:rotate]
    for i, opt in enumerate(options):
        opt["key"] = letters[i]
    correct_keys = [letters[(i - rotate) % 4] for i in range(len(corrects))]
    remapped = {}
    text_to_reason = {c["text"]: c.get("rationale") for c in ranked}
    correct_key_set = set(correct_keys)
    for opt in options:
        if opt["key"] not in correct_key_set and opt["text"] in text_to_reason:
            remapped[opt["key"]] = text_to_reason[opt["text"]]
    packed = _pack(
        stem_payload,
        options,
        {"keys": correct_keys, "texts": corrects},
        remapped,
        chunk_id,
    )
    packed = await adversarial_fix(packed, passage)
    return packed


def _distractor_needed(question_type: str, n_correct: int) -> int:
    if question_type == "multi_choice":
        return max(1, 4 - n_correct)
    return 3


def _correct_texts_from_question(question: dict) -> list[str]:
    texts = answer_texts((question.get("answer") or {}).get("texts") or [])
    if texts:
        return texts
    keys = set((question.get("answer") or {}).get("keys") or [])
    return answer_texts(
        [
            str(opt.get("text") or "")
            for opt in (question.get("options") or [])
            if isinstance(opt, dict) and opt.get("key") in keys
        ]
    )


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

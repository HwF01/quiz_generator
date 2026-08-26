from __future__ import annotations

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
        if not text or text == answer:
            continue
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
    raw = await complete_json(provider, prompt, user, temperature=0.7)
    data = parse_json(raw)
    cands = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(cands, list):
        return []
    return [c for c in cands if c.get("text")]


async def adversarial_fix(question: dict, passage: str) -> dict:
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
        return question
    options = list(question.get("options") or [])
    replacements = review.get("replacements") or {}
    for key in review.get("too_easy_keys") or []:
        repl = replacements.get(key)
        if not repl:
            continue
        for opt in options:
            if opt.get("key") == key:
                opt["text"] = repl.get("text") or opt["text"]
                rationale = question.get("distractor_rationale") or {}
                rationale[key] = repl.get("rationale") or rationale.get(key)
                question["distractor_rationale"] = rationale
    question["options"] = options
    if review.get("guessable"):
        scores = question.get("quality_scores") or {}
        scores["guessable"] = True
        question["quality_scores"] = scores
        question["needs_review"] = True
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
    if qtype == "fill_blank":
        texts = stem_payload.get("answer", {}).get("texts") or [answer]
        return _pack(stem_payload, None, {"texts": texts}, None, chunk_id)

    cands = await overgenerate(stem, answer, passage)
    filtered = filter_candidates(cands, answer=answer, stem=stem, passage=passage)
    if len(filtered) < 3:
        extra = await overgenerate(stem, answer, passage)
        filtered = filter_candidates(filtered + extra, answer=answer, stem=stem, passage=passage)
    ranked = rank_candidates(filtered, answer=answer, stem=stem, passage=passage)[:3]
    used_placeholder = False
    while len(ranked) < 3:
        used_placeholder = True
        ranked.append(
            {
                "text": f"与「{answer}」相关但条件不同的表述",
                "error_type": "同维混淆",
                "rationale": "同类概念，适用条件不同",
            }
        )
    letters = ["A", "B", "C", "D"]
    correct_idx = 0
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
    old_keys = ["A", "B", "C", "D"]
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
        needs_review=used_placeholder,
    )
    packed = await adversarial_fix(packed, passage)
    if used_placeholder:
        packed["needs_review"] = True
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
        "source_span": {
            "chunk_id": chunk_id,
            "quote": stem_payload.get("source_quote") or "",
        },
        "source_chunk_id": chunk_id,
        "needs_review": bool(needs_review or stem_payload.get("needs_review")),
        "quality_scores": {},
    }

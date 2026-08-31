from __future__ import annotations

import json
import re

from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, generator_provider
from app.services.prompt_loader import load_prompt


def _normalized(text: object) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _quote_in_passage(quote: object, passage: str) -> bool:
    normalized_quote = _normalized(quote)
    return bool(normalized_quote) and normalized_quote in _normalized(passage)


def valid_stem_payload(payload: object, passage: str) -> bool:
    if not isinstance(payload, dict):
        return False
    common = bool(
        str(payload.get("stem") or "").strip()
        and str(payload.get("explanation") or "").strip()
        and _quote_in_passage(payload.get("source_quote"), passage)
    )
    if not common:
        return False
    question_type = str(payload.get("type") or "")
    if question_type == "single_choice":
        return bool(str(payload.get("correct_text") or "").strip())
    if question_type == "multi_choice":
        return _valid_multi_correct_texts(payload.get("correct_texts"))
    if question_type == "true_false":
        keys = (payload.get("answer") or {}).get("keys") or []
        return bool(
            str(payload.get("correct_text") or "").strip()
            and len(keys) == 1
            and str(keys[0]) in {"对", "错"}
        )
    return _valid_constructed_answer(payload)


def _valid_multi_correct_texts(value: object) -> bool:
    if not isinstance(value, list) or len(value) not in {2, 3}:
        return False
    cleaned = [str(text).strip() for text in value]
    if any(not text for text in cleaned):
        return False
    norms = [_normalized(text) for text in cleaned]
    return len(set(norms)) == len(norms)


def _valid_constructed_answer(payload: dict) -> bool:
    subparts = payload.get("subparts")
    answers = (payload.get("answer") or {}).get("subparts")
    if not isinstance(subparts, list) or not isinstance(answers, list) or not subparts or not answers:
        return False
    answer_by_id = {
        str(answer.get("id")): answer for answer in answers if isinstance(answer, dict) and answer.get("id")
    }
    if len(answer_by_id) != len(answers):
        return False
    for part in subparts:
        if not isinstance(part, dict):
            return False
        part_id = str(part.get("id") or "")
        if not part_id or not str(part.get("prompt") or "").strip():
            return False
        answer = answer_by_id.get(part_id)
        if not answer:
            return False
        if payload.get("type") == "fill_blank":
            if not [text for text in answer.get("texts") or [] if str(text).strip()]:
                return False
        elif not [point for point in answer.get("expected_points") or [] if str(point).strip()]:
            return False
    return True


async def extract_key_items(passage: str, subject: str) -> list[dict]:
    provider = generator_provider(subject)
    prompt = load_prompt("extract_key_sentences")
    user = f"【待考查文本开始】\n{passage}\n【待考查文本结束】"
    for _ in range(2):
        try:
            raw = await complete_json(provider, prompt, user, temperature=0.2)
            data = parse_json(raw)
        except Exception:
            continue
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            continue
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if quote and answer and _quote_in_passage(quote, passage):
                cleaned.append({**item, "quote": quote, "answer": answer})
        if cleaned:
            return cleaned[:3]
    return []


async def generate_stem(
    passage: str,
    item: dict,
    alloc: dict,
    subject: str,
    external_sources: list[dict] | None = None,
) -> dict:
    provider = generator_provider(subject)
    prompt = load_prompt("generate_stem")
    source_context = ""
    if external_sources:
        source_context = (
            "\n【外部参考资料开始】\n"
            f"{json.dumps(external_sources, ensure_ascii=False)}\n"
            "【外部参考资料结束】\n"
        )
    user = (
        f"题型：{alloc['type']}\n微技能：{alloc['micro_skill']}\n难度：{alloc['difficulty']}\n"
        f"关键句：{item.get('quote')}\n预置答案锚点：{item.get('answer')}\n"
        f"【待考查文本开始】\n{passage}\n【待考查文本结束】{source_context}"
    )
    for _ in range(2):
        try:
            raw = await complete_json(provider, prompt, user, temperature=0.4)
            data = parse_json(raw)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        data["type"] = alloc["type"]
        data["micro_skill"] = alloc["micro_skill"]
        data["difficulty"] = alloc["difficulty"]
        data["target_difficulty"] = alloc.get("target_difficulty")
        data["cognitive_level"] = alloc.get("cognitive_level", "understand")
        data["external_source_ids"] = [
            str(source_id) for source_id in (data.get("external_source_ids") or []) if source_id
        ]
        if valid_stem_payload(data, passage):
            return data
    return {"_generation_error": "题干、正解、解析或来源证据不完整"}

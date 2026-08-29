from __future__ import annotations

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
    return bool(
        str(payload.get("stem") or "").strip()
        and str(payload.get("correct_text") or "").strip()
        and str(payload.get("explanation") or "").strip()
        and _quote_in_passage(payload.get("source_quote"), passage)
    )


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
) -> dict:
    provider = generator_provider(subject)
    prompt = load_prompt("generate_stem")
    user = (
        f"题型：{alloc['type']}\n微技能：{alloc['micro_skill']}\n难度：{alloc['difficulty']}\n"
        f"关键句：{item.get('quote')}\n预置答案锚点：{item.get('answer')}\n"
        f"【待考查文本开始】\n{passage}\n【待考查文本结束】"
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
        data["cognitive_level"] = alloc.get("cognitive_level", "understand")
        if valid_stem_payload(data, passage):
            return data
    return {"_generation_error": "题干、正解、解析或来源证据不完整"}

from __future__ import annotations

from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, generator_provider
from app.services.prompt_loader import load_prompt


async def extract_key_items(passage: str, subject: str) -> list[dict]:
    provider = generator_provider(subject)
    prompt = load_prompt("extract_key_sentences")
    user = f"【待考查文本开始】\n{passage}\n【待考查文本结束】"
    raw = await complete_json(provider, prompt, user, temperature=0.2)
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        data = parse_json(raw)
    except Exception:
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        quote = str(item.get("quote") or "").strip()
        if quote and quote in passage:
            item["quote"] = quote
            cleaned.append(item)
        elif quote:
            item["quote"] = quote
            cleaned.append(item)
    return cleaned[:3]


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
    raw = await complete_json(provider, prompt, user, temperature=0.6)
    data = parse_json(raw)
    data["type"] = alloc["type"]
    data["micro_skill"] = alloc["micro_skill"]
    data["difficulty"] = alloc["difficulty"]
    data["cognitive_level"] = alloc.get("cognitive_level", "understand")
    data["source_quote"] = data.get("source_quote") or item.get("quote")
    data["correct_text"] = data.get("correct_text") or item.get("answer") or ""
    return data

from __future__ import annotations

from app.services.chunking import Chunk
from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, generator_provider
from app.services.prompt_loader import load_prompt

STEM_SUBJECTS = {"it", "math", "logic"}


async def classify_subject(text: str, hint: str = "auto") -> str:
    if hint and hint not in ("auto", "general"):
        return hint
    provider = generator_provider("general")
    prompt = load_prompt("classify_subject")
    raw = await complete_json(
        provider,
        prompt,
        f"【待考查文本开始】\n{text[:3000]}\n【待考查文本结束】",
        temperature=0.2,
    )
    try:
        data = parse_json(raw)
        return str(data.get("subject") or "general")
    except Exception:
        return "general"


async def map_passages(chunks: list[Chunk], subject: str, target_grade: str) -> list[dict]:
    provider = generator_provider(subject)
    prompt = load_prompt("passage_map")
    mapped = []
    for chunk in chunks:
        user = (
            f"目标学段：{target_grade}\n科目：{subject}\n"
            f"【待考查文本开始】\n{chunk.text}\n【待考查文本结束】"
        )
        try:
            raw = await complete_json(provider, prompt, user, temperature=0.2)
            data = parse_json(raw)
        except Exception:
            data = {
                "unsuitable": len(chunk.text) < 60,
                "reason": "映射失败，按长度兜底",
                "suitable_skills": ["理解"],
                "suggested_types": ["single_choice"],
                "suggested_points": [],
                "summary": chunk.text[:80],
            }
        data["chunk_id"] = chunk.id
        data["text"] = chunk.text
        mapped.append(data)
    return mapped

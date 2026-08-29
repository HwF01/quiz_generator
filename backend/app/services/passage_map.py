from __future__ import annotations

import asyncio

from app.services.chunking import Chunk
from app.services.jsonutil import parse_json
from app.services.llm.router import complete_json, generator_provider
from app.services.prompt_loader import load_prompt
from app.services.blueprint import subject_tags_for

STEM_SUBJECTS = {"it", "math", "logic"}


async def classify_subject(text: str, hint: str = "auto") -> str:
    profile = await classify_subject_profile(text, hint)
    return profile["subject"]


async def classify_subject_profile(
    text: str, hint: str = "auto", overrides: list[str] | None = None
) -> dict:
    if hint and hint not in ("auto", "general"):
        subject = hint
        detected_tags: list[str] = []
    else:
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
            subject = str(data.get("subject") or "general")
            detected_tags = [str(tag) for tag in (data.get("subject_tags") or [])]
        except Exception:
            subject = "general"
            detected_tags = []
    return {
        "subject": subject,
        "subject_tags": subject_tags_for(subject, [*detected_tags, *(overrides or [])]),
    }


async def map_passages(chunks: list[Chunk], subject: str, target_grade: str) -> list[dict]:
    provider = generator_provider(subject)
    prompt = load_prompt("passage_map")

    async def map_one(chunk: Chunk) -> dict:
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
        return data

    semaphore = asyncio.Semaphore(4)

    async def guarded_map(chunk: Chunk) -> dict:
        async with semaphore:
            return await map_one(chunk)

    return list(await asyncio.gather(*(guarded_map(chunk) for chunk in chunks)))

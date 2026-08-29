from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.schemas.quiz import QuizBlueprint
from app.services.blueprint import allocate, allowed_question_types
from app.services.cache import content_hash
from app.services.chunking import split_paragraphs
from app.services.doc_parser import parse_document
from app.services.passage_map import classify_subject_profile, map_passages
from app.services.storage import download_bytes


async def prepare_generation_preview(
    db: AsyncSession,
    doc: Document,
    blueprint: QuizBlueprint,
    subject_hint: str = "auto",
) -> dict:
    if doc.extracted_text:
        text = doc.extracted_text
    else:
        data = await asyncio.to_thread(download_bytes, doc.object_key)
        parsed = await asyncio.to_thread(parse_document, doc.filename, data)
        if parsed.error and not parsed.text:
            raise RuntimeError(parsed.error)
        text = parsed.text
        doc.extracted_text = text
        doc.extracted_chars = len(text)
        doc.used_ocr = parsed.used_ocr
        doc.parse_error = parsed.error
        doc.content_hash = content_hash(text)
        doc.status = "parsed"

    profile = await classify_subject_profile(text[:4000], subject_hint, blueprint.subject_tags)
    chunks = split_paragraphs(text)
    mapped = await map_passages(chunks, profile["subject"], blueprint.target_grade)
    doc.passage_map = mapped
    await db.commit()

    suitable = [item for item in mapped if not item.get("unsuitable")]
    suggested_types = [
        kind
        for item in suitable
        for kind in (item.get("suggested_types") or [])
        if isinstance(kind, str)
    ]
    allocations = allocate(
        blueprint.total_questions,
        blueprint,
        subject_tags=profile["subject_tags"],
        suggested_types=suggested_types,
    )
    return {
        "subject": profile["subject"],
        "subject_tags": profile["subject_tags"],
        "available_question_types": allowed_question_types(profile["subject_tags"]),
        "suggested_type_counts": _type_counts(allocations),
        "suitable_passages": len(suitable),
        "capacity_hint": min(50, len(suitable) * 2),
    }


def _type_counts(allocations: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for allocation in allocations:
        kind = str(allocation["type"])
        counts[kind] = counts.get(kind, 0) + 1
    return counts

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.models.generation_job import GenerationJob
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.schemas.quiz import QuizBlueprint
from app.services.blueprint import allocate, enforce_detail_cap
from app.services.cache import content_hash, remember_doc_quiz, similar_doc_quiz
from app.services.chunking import split_paragraphs
from app.services.doc_parser import parse_document
from app.services.distractor_engine import build_choice_question
from app.services.passage_map import classify_subject, map_passages
from app.services.progress import set_progress
from app.services.quality_gates import apply_gates
from app.services.quiz_generator import extract_key_items, generate_stem
from app.services.quota import decr_quota
from app.services.storage import download_bytes
from app.services.llm.router import critic_provider, generator_provider

logger = logging.getLogger(__name__)
_GEN_SEM = asyncio.Semaphore(4)


async def _clone_questions(db: AsyncSession, src_quiz_id: str, dest_quiz_id: str) -> int:
    rows = await db.execute(select(Question).where(Question.quiz_set_id == src_quiz_id))
    n = 0
    for q in rows.scalars().all():
        db.add(
            Question(
                quiz_set_id=dest_quiz_id,
                type=q.type,
                content=q.content,
                options=q.options,
                answer=q.answer,
                explanation=q.explanation,
                distractor_rationale=q.distractor_rationale,
                difficulty=q.difficulty,
                knowledge_tags=q.knowledge_tags,
                micro_skill=q.micro_skill,
                cognitive_level=q.cognitive_level,
                source_span=q.source_span,
                quality_scores=q.quality_scores,
                needs_review=q.needs_review,
                source_chunk_id=q.source_chunk_id,
            )
        )
        n += 1
    return n


async def run_generation(db: AsyncSession, job_id: str) -> None:
    job = await db.get(GenerationJob, job_id)
    if not job:
        return
    if job.status == "succeeded":
        return
    doc = await db.get(Document, job.document_id)
    quiz = await db.get(QuizSet, job.quiz_set_id) if job.quiz_set_id else None
    try:
        await set_progress(db, job, 5, "解析文档", "running")
        data = await asyncio.to_thread(download_bytes, doc.object_key)
        parsed = await asyncio.to_thread(parse_document, doc.filename, data)
        if parsed.error and not parsed.text:
            raise RuntimeError(parsed.error)
        doc.extracted_text = parsed.text
        doc.extracted_chars = len(parsed.text)
        doc.used_ocr = parsed.used_ocr
        doc.content_hash = content_hash(parsed.text)
        doc.status = "parsed"
        await db.commit()

        cfg = job.config or {}
        force = bool(cfg.get("force"))
        reused_id = None
        if doc.content_hash and not force:
            try:
                reused_id = await similar_doc_quiz(doc.content_hash)
            except Exception:
                reused_id = None
        if reused_id and quiz and reused_id != quiz.id:
            await set_progress(db, job, 40, "命中相似文档，复用已有题库")
            await db.execute(delete(Question).where(Question.quiz_set_id == quiz.id))
            n = await _clone_questions(db, reused_id, quiz.id)
            if n:
                quiz.question_count = n
                quiz.status = "ready"
                job.models_used = {**(job.models_used or {}), "reused_quiz_id": reused_id}
                await db.commit()
                await set_progress(db, job, 100, "完成（复用已有题库）", "succeeded")
                return

        subject_hint = cfg.get("subject") or "auto"
        blueprint = QuizBlueprint.model_validate(cfg.get("blueprint") or {})
        await set_progress(db, job, 15, "科目识别与篇章映射")
        subject = await classify_subject(parsed.text[:4000], subject_hint)
        if quiz:
            quiz.subject = subject
        chunks = split_paragraphs(parsed.text)
        mapped = await map_passages(chunks, subject, blueprint.target_grade)
        doc.passage_map = mapped
        await db.commit()

        suitable = [m for m in mapped if not m.get("unsuitable")]
        if not suitable:
            raise RuntimeError("文档中没有适合出题的段落，请检查材料或换一份文档")

        await set_progress(db, job, 30, "抽取关键句")
        key_items: list[dict] = []
        for m in suitable:
            items = await extract_key_items(m["text"], subject)
            for it in items:
                it["chunk_id"] = m["chunk_id"]
                it["passage"] = m["text"]
                key_items.append(it)
            if len(key_items) >= settings.max_key_sentences:
                break
        if not key_items:
            for m in suitable[: blueprint.total_questions]:
                key_items.append(
                    {
                        "quote": m["text"][:80],
                        "answer": (m.get("summary") or m["text"])[:20],
                        "chunk_id": m["chunk_id"],
                        "passage": m["text"],
                        "knowledge_tags": m.get("suggested_points") or [],
                    }
                )

        allocs = allocate(len(key_items), blueprint)
        key_items = key_items[: len(allocs)]
        gen = generator_provider(subject)
        cri = critic_provider()
        job.models_used = {
            "generator": getattr(gen, "name", "generator"),
            "generator_model": getattr(gen, "model", ""),
            "critic": getattr(cri, "name", "critic"),
            "critic_model": getattr(cri, "model", ""),
            "subject": subject,
        }
        await db.commit()

        total = max(len(key_items), 1)
        target = min(blueprint.total_questions, settings.max_questions)

        async def _build_one(i: int, item: dict, alloc) -> dict:
            async with _GEN_SEM:
                passage = item["passage"]
                stem = await generate_stem(passage, item, alloc, subject)
                q = await build_choice_question(stem, passage, item["chunk_id"])
                return await apply_gates(q, passage)

        built = await asyncio.gather(
            *[_build_one(i, item, alloc) for i, (item, alloc) in enumerate(zip(key_items, allocs))]
        )
        questions = list(built)[:target]
        await set_progress(db, job, 85, f"出题完成 {len(questions)}/{total}")

        questions = enforce_detail_cap(questions, blueprint.max_detail_ratio)
        await set_progress(db, job, 90, "写入题库")
        if quiz is None:
            raise RuntimeError("题库记录缺失")
        await db.execute(delete(Question).where(Question.quiz_set_id == quiz.id))
        for q in questions:
            db.add(
                Question(
                    quiz_set_id=quiz.id,
                    type=q.get("type") or "single_choice",
                    content=q.get("content") or "",
                    options=q.get("options"),
                    answer=q.get("answer") or {},
                    explanation=q.get("explanation"),
                    distractor_rationale=q.get("distractor_rationale"),
                    difficulty=q.get("difficulty") or "medium",
                    knowledge_tags=q.get("knowledge_tags") or [],
                    micro_skill=q.get("micro_skill") or "detail",
                    cognitive_level=q.get("cognitive_level") or "remember",
                    source_span=q.get("source_span"),
                    quality_scores=q.get("quality_scores"),
                    needs_review=bool(q.get("needs_review")),
                    source_chunk_id=q.get("source_chunk_id"),
                )
            )
        quiz.question_count = len(questions)
        quiz.status = "ready"
        quiz.subject = subject
        quiz.blueprint = blueprint.model_dump()
        await remember_doc_quiz(doc.content_hash, quiz.id)
        await db.commit()
        await set_progress(db, job, 100, "完成", "succeeded")
    except Exception as exc:
        logger.exception("generation failed job=%s", job_id)
        job.error = str(exc)
        job.status = "failed"
        if quiz:
            quiz.status = "failed"
        await db.commit()
        try:
            await decr_quota(job.user_id)
        except Exception:
            logger.exception("quota refund failed job=%s", job_id)
        await set_progress(db, job, job.progress or 0, "失败", "failed")
        raise

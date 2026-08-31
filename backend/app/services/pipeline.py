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
from app.services.distractor_engine import build_choice_question
from app.services.generation_preview import prepare_generation_preview
from app.services.progress import set_progress
from app.services.quality_gates import apply_gates
from app.services.quiz_generator import extract_key_items, generate_stem
from app.services.quota import decr_quota
from app.services.llm.router import assign_roles
from app.services.subjective_grading import build_grading_rubric
from app.services.web_search import search_related_knowledge, topic_queries

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
                subparts=q.subparts,
                source_span=q.source_span,
                external_sources=q.external_sources,
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
        cfg = job.config or {}
        force = bool(cfg.get("force"))
        blueprint = QuizBlueprint.model_validate(cfg.get("blueprint") or {})
        subject_hint = cfg.get("subject") or "auto"
        preview = await prepare_generation_preview(db, doc, blueprint, subject_hint)
        subject = preview["subject"]
        resolved_tags = preview["subject_tags"]
        blueprint = blueprint.model_copy(update={"subject_tags": resolved_tags})
        mapped = doc.passage_map or []
        parsed_text = doc.extracted_text or ""
        cache_config = {
            "subject": subject,
            "blueprint": blueprint.model_dump(mode="json"),
        }
        if quiz:
            quiz.subject = subject
            quiz.blueprint = blueprint.model_dump(mode="json")
            if quiz.status != "ready":
                quiz.status = "generating"

        reused_id = None
        if doc.content_hash and not force:
            try:
                reused_id = await similar_doc_quiz(job.user_id, doc.content_hash, cache_config)
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

        await set_progress(db, job, 15, "科目识别与篇章映射")

        suitable = [m for m in mapped if not m.get("unsuitable")]
        if not suitable:
            raise RuntimeError("文档中没有适合出题的段落，请检查材料或换一份文档")

        await set_progress(db, job, 30, "抽取关键句")
        async def extract_for_passage(passage: dict) -> list[dict]:
            async with _GEN_SEM:
                return await extract_key_items(passage["text"], subject)

        selected_passages = suitable[: settings.max_key_sentences]
        extracted = await asyncio.gather(
            *(extract_for_passage(passage) for passage in selected_passages)
        )
        key_items: list[dict] = []
        for m, items in zip(selected_passages, extracted):
            for it in items:
                it["chunk_id"] = m["chunk_id"]
                it["passage"] = m["text"]
                key_items.append(it)
        unique_items: list[dict] = []
        seen_quotes: set[str] = set()
        for item in key_items:
            quote = "".join(str(item.get("quote") or "").split())
            if quote and quote not in seen_quotes:
                seen_quotes.add(quote)
                unique_items.append(item)
        target = blueprint.total_questions
        key_items = unique_items[:target]
        suggested_types = [
            kind
            for item in suitable
            for kind in (item.get("suggested_types") or [])
            if isinstance(kind, str)
        ]
        allocs = allocate(
            len(key_items),
            blueprint,
            subject_tags=resolved_tags,
            suggested_types=suggested_types,
        )
        roles = assign_roles(subject)
        gen, cri = roles.generator, roles.critic
        job.models_used = {
            "generator": getattr(gen, "name", "generator"),
            "generator_model": getattr(gen, "model", ""),
            "critic": getattr(cri, "name", "critic"),
            "critic_model": getattr(cri, "model", ""),
            "subject": subject,
            "subject_tags": resolved_tags,
            "self_review": "true" if roles.self_review else "false",
        }
        if len(key_items) < target:
            job.models_used["shortfall_reason"] = "可溯源关键句不足，已按质量优先减少题量"
        await db.commit()

        total = len(key_items)
        if not key_items:
            raise RuntimeError("未能从材料中提取可溯源的考查内容，请补充更完整的教学文本")

        external_sources: list[dict] = []
        if blueprint.enable_web_search:
            await set_progress(db, job, 35, "检索补充知识")
            external_sources = await search_related_knowledge(topic_queries(key_items, subject))
            job.models_used = {
                **(job.models_used or {}),
                "web_search": "tavily",
                "web_sources": str(len(external_sources)),
            }
            await db.commit()

        async def _build_one(i: int, item: dict, alloc) -> dict | None:
            async with _GEN_SEM:
                passage = item["passage"]
                stem = await generate_stem(passage, item, alloc, subject, external_sources)
                if stem.get("_generation_error"):
                    logger.warning("skip incomplete stem job=%s item=%s", job_id, i)
                    return None
                q = await build_choice_question(stem, passage, item["chunk_id"], subject=subject)
                source_ids = set(stem.get("external_source_ids") or [])
                known_ids = {source["id"] for source in external_sources}
                if source_ids - known_ids:
                    q["needs_review"] = True
                    scores = q.get("quality_scores") or {}
                    scores["review_reasons"] = [
                        *scores.get("review_reasons", []),
                        "invalid_external_source",
                    ]
                    q["quality_scores"] = scores
                q["external_sources"] = [
                    {**source, "used": source["id"] in source_ids}
                    for source in external_sources
                    if source["id"] in source_ids
                ]
                q = await build_grading_rubric(q, passage, subject=subject)
                return await apply_gates(
                    q, passage, subject_tags=resolved_tags, subject=subject
                )

        built = await asyncio.gather(
            *[_build_one(i, item, alloc) for i, (item, alloc) in enumerate(zip(key_items, allocs))]
        )
        questions = [q for q in built if q is not None][:target]
        if not questions:
            raise RuntimeError("未能生成可溯源题目，请补充更完整的教学文本后重试")
        job.models_used = {
            **(job.models_used or {}),
            "requested_questions": str(target),
            "generated_questions": str(len(questions)),
            "skipped_questions": str(target - len(questions)),
        }
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
                    subparts=q.get("subparts"),
                    source_span=q.get("source_span"),
                    external_sources=q.get("external_sources"),
                    quality_scores=q.get("quality_scores"),
                    needs_review=bool(q.get("needs_review")),
                    source_chunk_id=q.get("source_chunk_id"),
                )
            )
        quiz.question_count = len(questions)
        quiz.status = "ready"
        quiz.subject = subject
        quiz.blueprint = blueprint.model_dump(mode="json")
        if any(question.get("needs_review") for question in questions):
            quiz.visibility = "private"
            quiz.is_public = False
        await remember_doc_quiz(job.user_id, doc.content_hash or content_hash(parsed_text), cache_config, quiz.id)
        await db.commit()
        await set_progress(
            db,
            job,
            100,
            f"完成：生成 {len(questions)}/{target} 题，跳过 {target - len(questions)} 题",
            "succeeded",
        )
    except Exception as exc:
        logger.exception("generation failed job=%s", job_id)
        job.error = str(exc)
        job.status = "failed"
        if quiz:
            job.quiz_set_id = None
            quiz.generation_job_id = None
            await db.delete(quiz)
        await db.commit()
        try:
            await decr_quota(job.user_id)
        except Exception:
            logger.exception("quota refund failed job=%s", job_id)
        await set_progress(db, job, job.progress or 0, "失败", "failed")
        raise

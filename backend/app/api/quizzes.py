import asyncio
from typing import Literal

from arq import create_pool
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import assert_quiz_accessible
from app.core.arq import redis_settings
from app.core.config import settings
from app.core.deps import get_current_user, get_optional_user
from app.core.exceptions import AppError, ok
from app.db.session import get_db
from app.models.document import Document
from app.models.favorite import Favorite
from app.models.generation_job import GenerationJob
from app.models.question import Question
from app.models.quiz_rating import QuizRating
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.schemas.quiz import GenerateQuizIn, QuestionUpdateIn, QuizUpdateIn, RatingIn
from app.services.distractor_engine import build_choice_question
from app.services.quality_gates import apply_gates
from app.services.quota import assert_quota, incr_quota

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def _q_out(q: Question) -> dict:
    return {
        "id": q.id,
        "type": q.type,
        "content": q.content,
        "options": q.options,
        "answer": q.answer,
        "explanation": q.explanation,
        "distractor_rationale": q.distractor_rationale,
        "difficulty": q.difficulty,
        "knowledge_tags": q.knowledge_tags,
        "micro_skill": q.micro_skill,
        "cognitive_level": q.cognitive_level,
        "source_span": q.source_span,
        "quality_scores": q.quality_scores,
        "needs_review": q.needs_review,
    }


def _quiz_out(quiz: QuizSet, extra: dict | None = None) -> dict:
    data = {
        "id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "category": quiz.category,
        "subject": quiz.subject,
        "visibility": quiz.visibility,
        "is_public": quiz.is_public,
        "is_builtin": quiz.is_builtin,
        "status": quiz.status,
        "question_count": quiz.question_count,
        "likes": quiz.likes,
        "plays": quiz.plays,
        "creator_id": quiz.creator_id,
        "generation_job_id": quiz.generation_job_id,
        "blueprint": quiz.blueprint,
        "created_at": quiz.created_at.isoformat() if quiz.created_at else None,
    }
    if extra:
        data.update(extra)
    return data


@router.post("/generate")
async def generate(
    body: GenerateQuizIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await assert_quota(user.id, user.daily_gen_quota)
    doc = await db.get(Document, body.document_id)
    if not doc or doc.owner_id != user.id:
        raise AppError("文档不存在", code=404, status_code=404)
    job = GenerationJob(
        user_id=user.id,
        document_id=doc.id,
        status="queued",
        stage="queued",
        config=body.model_dump(),
    )
    db.add(job)
    await db.flush()
    quiz = QuizSet(
        creator_id=user.id,
        document_id=doc.id,
        generation_job_id=job.id,
        title=body.title,
        category=body.category,
        subject=body.subject if body.subject != "auto" else "general",
        visibility=body.visibility,
        is_public=body.visibility == "public",
        status="draft",
        blueprint=body.blueprint.model_dump(),
    )
    db.add(quiz)
    await db.flush()
    job.quiz_set_id = quiz.id
    await db.commit()

    async def _run() -> None:
        from app.db.session import SessionLocal
        from app.services.pipeline import run_generation

        async with SessionLocal() as session:
            await run_generation(session, job.id)

    local_fallback = settings.is_local_stack
    if local_fallback:
        asyncio.create_task(_run())
    else:
        try:
            pool = await create_pool(redis_settings())
            await pool.enqueue_job("generate_quiz_job", job.id)
            await pool.aclose()
        except Exception as exc:
            job.status = "failed"
            job.error = "任务队列暂不可用"
            quiz.status = "failed"
            await db.commit()
            raise AppError("任务队列暂不可用，请稍后重试", code=503, status_code=503) from exc
    await incr_quota(user.id, user.daily_gen_quota)
    return ok({"job_id": job.id, "quiz_id": quiz.id})


@router.get("/favorites")
async def my_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(select(Favorite).where(Favorite.user_id == user.id))
    out = []
    for fav in rows.scalars().all():
        quiz = await db.get(QuizSet, fav.quiz_set_id)
        if quiz:
            out.append(_quiz_out(quiz))
    return ok(out)


@router.get("")
async def my_quizzes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(QuizSet)
        .where(QuizSet.creator_id == user.id)
        .order_by(QuizSet.created_at.desc())
    )
    return ok([_quiz_out(q) for q in rows.scalars().all()])


@router.get("/{quiz_id}")
async def get_quiz(
    quiz_id: str,
    purpose: Literal["practice", "review"] = Query("practice"),
    hide_answer: bool = False,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    assert_quiz_accessible(quiz, user)
    qrows = await db.execute(
        select(Question).where(Question.quiz_set_id == quiz.id).order_by(Question.created_at)
    )
    questions = [_q_out(q) for q in qrows.scalars().all()]
    is_owner = bool(user and quiz.creator_id == user.id)
    strip = (purpose != "review" or not is_owner) or hide_answer
    if strip:
        for q in questions:
            q.pop("answer", None)
            q.pop("explanation", None)
            q.pop("distractor_rationale", None)
            q.pop("quality_scores", None)
    return ok(_quiz_out(quiz, {"questions": questions}))


@router.patch("/{quiz_id}")
async def patch_quiz(
    quiz_id: str,
    body: QuizUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    if not quiz or quiz.creator_id != user.id:
        raise AppError("无权修改", code=403, status_code=403)
    if quiz.is_builtin:
        raise AppError("内置题库不可修改", code=403, status_code=403)
    if body.title is not None:
        quiz.title = body.title
    if body.description is not None:
        quiz.description = body.description
    if body.category is not None:
        quiz.category = body.category
    if body.visibility is not None:
        quiz.visibility = body.visibility
        quiz.is_public = body.visibility == "public"
    await db.commit()
    return ok(_quiz_out(quiz))


@router.delete("/{quiz_id}")
async def delete_quiz(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    if not quiz or quiz.creator_id != user.id:
        raise AppError("无权删除", code=403, status_code=403)
    if quiz.is_builtin:
        raise AppError("内置题库不可删除", code=403, status_code=403)
    await db.delete(quiz)
    await db.commit()
    return ok(True)


@router.patch("/questions/{question_id}")
async def patch_question(
    question_id: str,
    body: QuestionUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await db.get(Question, question_id)
    if not q:
        raise AppError("题目不存在", code=404, status_code=404)
    quiz = await db.get(QuizSet, q.quiz_set_id)
    if not quiz or quiz.creator_id != user.id:
        raise AppError("无权修改", code=403, status_code=403)
    if quiz.is_builtin:
        raise AppError("内置题库不可修改", code=403, status_code=403)
    for field in ("content", "options", "answer", "explanation", "needs_review"):
        val = getattr(body, field)
        if val is not None:
            setattr(q, field, val)
    await db.commit()
    return ok(_q_out(q))


@router.delete("/questions/{question_id}")
async def delete_question(
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await db.get(Question, question_id)
    if not q:
        raise AppError("题目不存在", code=404, status_code=404)
    quiz = await db.get(QuizSet, q.quiz_set_id)
    if not quiz or quiz.creator_id != user.id:
        raise AppError("无权删除", code=403, status_code=403)
    if quiz.is_builtin:
        raise AppError("内置题库不可删除", code=403, status_code=403)
    await db.delete(q)
    quiz.question_count = max((quiz.question_count or 1) - 1, 0)
    await db.commit()
    return ok(True)


@router.post("/questions/{question_id}/harden")
async def harden_question(
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await db.get(Question, question_id)
    if not q:
        raise AppError("题目不存在", code=404, status_code=404)
    quiz = await db.get(QuizSet, q.quiz_set_id)
    if not quiz or quiz.creator_id != user.id:
        raise AppError("无权操作", code=403, status_code=403)
    if quiz.is_builtin:
        raise AppError("内置题库不可修改", code=403, status_code=403)
    span = q.source_span or {}
    passage = span.get("quote") or q.content
    stem = {
        "stem": q.content,
        "type": q.type,
        "correct_text": (q.answer or {}).get("texts", [""])[0]
        if q.type != "true_false"
        else "true",
        "answer": q.answer,
        "explanation": q.explanation,
        "knowledge_tags": q.knowledge_tags,
        "micro_skill": q.micro_skill,
        "difficulty": q.difficulty,
        "cognitive_level": q.cognitive_level,
        "source_quote": span.get("quote"),
    }
    if q.options:
        correct_keys = (q.answer or {}).get("keys") or []
        for opt in q.options:
            if opt.get("key") in correct_keys:
                stem["correct_text"] = opt.get("text")
    rebuilt = await build_choice_question(stem, passage, q.source_chunk_id or "")
    rebuilt = await apply_gates(rebuilt, passage)
    q.options = rebuilt.get("options")
    q.answer = rebuilt.get("answer") or q.answer
    q.distractor_rationale = rebuilt.get("distractor_rationale")
    q.quality_scores = rebuilt.get("quality_scores")
    q.needs_review = bool(rebuilt.get("needs_review"))
    await db.commit()
    return ok(_q_out(q))


@router.post("/{quiz_id}/favorite")
async def toggle_favorite(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    assert_quiz_accessible(quiz, user)
    existing = await db.get(Favorite, (user.id, quiz_id))
    if existing:
        await db.delete(existing)
        quiz.likes = max(quiz.likes - 1, 0)
        await db.commit()
        return ok({"favorited": False})
    db.add(Favorite(user_id=user.id, quiz_set_id=quiz_id))
    quiz.likes += 1
    await db.commit()
    return ok({"favorited": True})


@router.post("/{quiz_id}/rate")
async def rate_quiz(
    quiz_id: str,
    body: RatingIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    assert_quiz_accessible(quiz, user)
    existing = await db.get(QuizRating, (user.id, quiz_id))
    if existing:
        existing.score = body.score
        existing.comment = body.comment
    else:
        db.add(
            QuizRating(
                user_id=user.id, quiz_set_id=quiz_id, score=body.score, comment=body.comment
            )
        )
    await db.commit()
    avg = await db.scalar(
        select(func.avg(QuizRating.score)).where(QuizRating.quiz_set_id == quiz_id)
    )
    return ok({"avg": float(avg or 0), "my_score": body.score})

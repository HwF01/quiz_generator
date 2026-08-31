import logging
from typing import Literal

from arq import create_pool
from fastapi import APIRouter, BackgroundTasks, Depends, Query
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
from app.models.question_favorite import QuestionFavorite
from app.models.quiz_rating import QuizRating
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.schemas.quiz import GenerateQuizIn, QuestionUpdateIn, QuizUpdateIn, RatingIn
from app.services.blueprint import subject_tags_for, validate_type_counts
from app.services.distractor_engine import build_choice_question
from app.services.quality_gates import apply_gates, choice_structure_valid, is_practice_eligible
from app.services.quota import assert_quota, incr_quota
from app.services.quiz_title import uniquify_title
from app.services.subjective_grading import is_constructed, rubric_valid

logger = logging.getLogger("quizgen")
router = APIRouter(prefix="/quizzes", tags=["quizzes"])


async def _run_generation_job(job_id: str) -> None:
    from app.db.session import SessionLocal
    from app.services.pipeline import run_generation

    try:
        async with SessionLocal() as session:
            await run_generation(session, job_id)
    except Exception:
        logger.exception("generation job failed job_id=%s", job_id)


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
        "subparts": q.subparts,
        "source_span": q.source_span,
        "external_sources": q.external_sources,
        "quality_scores": q.quality_scores,
        "needs_review": q.needs_review,
    }


async def _discard_quiz(db: AsyncSession, quiz: QuizSet, job: GenerationJob | None = None) -> None:
    if job is not None:
        job.quiz_set_id = None
    elif quiz.generation_job_id:
        linked = await db.get(GenerationJob, quiz.generation_job_id)
        if linked:
            linked.quiz_set_id = None
    quiz.generation_job_id = None
    await db.delete(quiz)


def _source_passage(doc: Document | None, question: Question) -> str:
    mapped = (doc.passage_map if doc else None) or []
    if isinstance(mapped, list):
        for item in mapped:
            if isinstance(item, dict) and item.get("chunk_id") == question.source_chunk_id:
                text = str(item.get("text") or "").strip()
                if text:
                    return text
    return str((doc.extracted_text if doc else "") or (question.source_span or {}).get("quote") or question.content)


async def _question_counts(db: AsyncSession, quiz_ids: list[str]) -> dict[str, int]:
    if not quiz_ids:
        return {}
    rows = await db.execute(
        select(Question.quiz_set_id, func.count())
        .where(Question.quiz_set_id.in_(quiz_ids))
        .group_by(Question.quiz_set_id)
    )
    return {quiz_id: int(n) for quiz_id, n in rows.all()}


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
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await assert_quota(user.id, user.daily_gen_quota)
    if body.blueprint.enable_web_search and not settings.web_search_available:
        raise AppError("未填写 Tavily Key，联网补充不可用；普通出题不受影响", code=503, status_code=503)
    if body.blueprint.allocation_mode == "manual":
        try:
            validate_type_counts(
                body.blueprint.type_counts,
                body.blueprint.subject_tags or subject_tags_for(body.subject),
            )
        except ValueError as exc:
            raise AppError(str(exc), code=400) from exc
    doc = await db.get(Document, body.document_id)
    if not doc or doc.owner_id != user.id:
        raise AppError("文档不存在", code=404, status_code=404)
    existing_titles = list(
        (
            await db.execute(
                select(QuizSet.title).where(
                    QuizSet.creator_id == user.id,
                    QuizSet.status != "failed",
                )
            )
        ).scalars().all()
    )
    resolved_title = uniquify_title(body.title, existing_titles)
    job_config = body.model_dump()
    job_config["title"] = resolved_title
    job = GenerationJob(
        user_id=user.id,
        document_id=doc.id,
        status="queued",
        stage="queued",
        config=job_config,
    )
    db.add(job)
    await db.flush()
    quiz = QuizSet(
        creator_id=user.id,
        document_id=doc.id,
        generation_job_id=job.id,
        title=resolved_title,
        category=body.category,
        subject=body.subject if body.subject != "auto" else "general",
        visibility=body.visibility,
        is_public=body.visibility == "public",
        status="generating",
        blueprint=body.blueprint.model_dump(),
    )
    db.add(quiz)
    await db.flush()
    job.quiz_set_id = quiz.id
    await db.commit()
    job_id = job.id
    quiz_id = quiz.id

    local_fallback = settings.is_local_stack
    if not local_fallback:
        try:
            pool = await create_pool(redis_settings())
            await pool.enqueue_job("generate_quiz_job", job_id)
            await pool.aclose()
        except Exception as exc:
            job.status = "failed"
            job.error = "任务队列暂不可用"
            await _discard_quiz(db, quiz, job)
            await db.commit()
            raise AppError("任务队列暂不可用，请稍后重试", code=503, status_code=503) from exc
    await incr_quota(user.id, user.daily_gen_quota)
    if local_fallback:
        background.add_task(_run_generation_job, job_id)
    return ok({"job_id": job_id, "quiz_id": quiz_id})


async def _favorited_quiz_ids(db: AsyncSession, user_id: str, quiz_ids: list[str]) -> set[str]:
    if not quiz_ids:
        return set()
    rows = await db.execute(
        select(Favorite.quiz_set_id).where(
            Favorite.user_id == user_id,
            Favorite.quiz_set_id.in_(quiz_ids),
        )
    )
    return set(rows.scalars().all())


@router.get("/favorites")
async def my_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(QuizSet)
        .join(Favorite, Favorite.quiz_set_id == QuizSet.id)
        .where(Favorite.user_id == user.id, QuizSet.status != "failed")
    )
    quizzes = list(rows.scalars().all())
    counts = await _question_counts(db, [q.id for q in quizzes])
    return ok([_quiz_out(quiz, {"favorited": True, "question_count": counts.get(quiz.id, 0)}) for quiz in quizzes])



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
    quizzes = list(rows.scalars().all())
    visible = [q for q in quizzes if q.status != "failed"]
    fav_ids = await _favorited_quiz_ids(db, user.id, [q.id for q in visible])
    counts = await _question_counts(db, [q.id for q in visible])
    return ok([_quiz_out(q, {"favorited": q.id in fav_ids, "question_count": counts.get(q.id, 0)}) for q in visible])



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
    actual_count = len(questions)
    if purpose == "practice":
        questions = [q for q in questions if is_practice_eligible(q)]
    fav_ids: set[str] = set()
    if user and questions:
        fav_rows = await db.execute(
            select(QuestionFavorite.question_id).where(
                QuestionFavorite.user_id == user.id,
                QuestionFavorite.question_id.in_([q["id"] for q in questions]),
            )
        )
        fav_ids = set(fav_rows.scalars().all())
    for q in questions:
        q["favorited"] = q["id"] in fav_ids
    is_owner = bool(user and quiz.creator_id == user.id)
    strip = (purpose != "review" or not is_owner) or hide_answer
    if strip:
        for q in questions:
            q.pop("answer", None)
            q.pop("explanation", None)
            q.pop("distractor_rationale", None)
            q.pop("quality_scores", None)
            q.pop("source_span", None)
            q.pop("external_sources", None)
            if q.get("subparts"):
                q["subparts"] = [
                    {"id": part.get("id"), "prompt": part.get("prompt")}
                    for part in q["subparts"]
                    if isinstance(part, dict)
                ]
    return ok(_quiz_out(quiz, {"questions": questions, "question_count": actual_count}))


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
        if body.visibility == "public":
            pending = await db.scalar(
                select(Question.id)
                .where(Question.quiz_set_id == quiz.id, Question.needs_review.is_(True))
                .limit(1)
            )
            if pending:
                raise AppError("题库仍有待审校题目，完成审校后才能公开", code=400)
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
    candidate = {
        "type": q.type,
        "options": body.options if body.options is not None else q.options,
        "answer": body.answer if body.answer is not None else q.answer,
        "subparts": body.subparts if body.subparts is not None else q.subparts,
    }
    structure_ok = choice_structure_valid(candidate)
    rubric_ok = not is_constructed(candidate) or rubric_valid(candidate.get("subparts"))
    if body.needs_review is False and (not structure_ok or not rubric_ok):
        if is_constructed(candidate):
            raise AppError("请先补全小问、正解和评分量规，再标记已审", code=400)
        if candidate.get("type") == "true_false":
            raise AppError("请先补全对/错选项并指定唯一正解，再标记已审", code=400)
        raise AppError("请先补全 4 个不同选项并指定唯一正解，再标记已审", code=400)
    for field in (
        "content",
        "options",
        "answer",
        "explanation",
        "subparts",
        "external_sources",
        "needs_review",
    ):
        val = getattr(body, field)
        if val is not None:
            setattr(q, field, val)
    if not structure_ok or not rubric_ok:
        scores = q.quality_scores or {}
        reasons = list(scores.get("review_reasons") or [])
        if "invalid_choice_structure" not in reasons:
            reasons.append("invalid_choice_structure")
        if not rubric_ok and "invalid_grading_rubric" not in reasons:
            reasons.append("invalid_grading_rubric")
        scores["review_reasons"] = reasons
        q.quality_scores = scores
        q.needs_review = True
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


@router.post("/questions/{question_id}/favorite")
async def toggle_question_favorite(
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = await db.get(Question, question_id)
    if not q:
        raise AppError("题目不存在", code=404, status_code=404)
    quiz = await db.get(QuizSet, q.quiz_set_id)
    assert_quiz_accessible(quiz, user)
    existing = await db.get(QuestionFavorite, (user.id, question_id))
    if existing:
        await db.delete(existing)
        await db.commit()
        favorited = False
    else:
        db.add(
            QuestionFavorite(
                user_id=user.id, question_id=question_id, quiz_set_id=q.quiz_set_id
            )
        )
        await db.commit()
        favorited = True
    return ok({"favorited": favorited})


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
    if q.type != "single_choice":
        raise AppError("仅单选题支持重新生成干扰项", code=400)
    span = q.source_span or {}
    doc = await db.get(Document, quiz.document_id) if quiz.document_id else None
    passage = _source_passage(doc, q)
    stem = {
        "stem": q.content,
        "type": q.type,
        "correct_text": (q.answer or {}).get("texts", [""])[0]
        if q.type != "true_false"
        else ((q.answer or {}).get("keys") or ["对"])[0],
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
    quiz = assert_quiz_accessible(quiz, user)
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
    shared_to_plaza = bool(quiz.is_builtin or quiz.is_public or quiz.visibility == "public")
    if not quiz.is_builtin and (quiz.visibility == "public" or quiz.is_public):
        quiz.visibility = "public"
        quiz.is_public = True
    await db.commit()
    avg = await db.scalar(
        select(func.avg(QuizRating.score)).where(QuizRating.quiz_set_id == quiz_id)
    )
    return ok({"avg": float(avg or 0), "my_score": body.score, "shared_to_plaza": shared_to_plaza})

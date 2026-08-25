from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.acl import assert_quiz_accessible
from app.core.deps import get_current_user
from app.core.exceptions import AppError, ok
from app.core.redis import get_redis
from app.db.session import get_db
from app.models.play_record import PlayRecord
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.models.wrong_question import WrongQuestion
from app.schemas.quiz import PlaySubmitIn
from app.services.knowledge_tracing import apply_play, recommend_difficulty

router = APIRouter(tags=["practice"])


def _is_correct(question: Question, user_answer) -> bool:
    answer = question.answer or {}
    if question.type == "fill_blank":
        texts = [str(t).strip().lower() for t in (answer.get("texts") or [])]
        return str(user_answer or "").strip().lower() in texts
    keys = [str(k) for k in (answer.get("keys") or [])]
    if isinstance(user_answer, list):
        return sorted(map(str, user_answer)) == sorted(keys)
    return str(user_answer) in keys


@router.post("/plays/{quiz_id}")
async def submit_play(
    quiz_id: str,
    body: PlaySubmitIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz = await db.get(QuizSet, quiz_id)
    assert_quiz_accessible(quiz, user)
    rows = await db.execute(select(Question).where(Question.quiz_set_id == quiz_id))
    questions = list(rows.scalars().all())
    if not questions:
        raise AppError("题库没有题目")
    if body.question_ids is not None:
        wanted = set(body.question_ids)
        questions = [q for q in questions if q.id in wanted]
        if not questions:
            raise AppError("题目不存在或不属于该题库")
    details = []
    skill_results: dict[str, list[bool]] = {}
    correct_n = 0
    for q in questions:
        ua = body.answers.get(q.id)
        ok_flag = _is_correct(q, ua)
        if ok_flag:
            correct_n += 1
        else:
            existing = await db.get(WrongQuestion, (user.id, q.id))
            if existing:
                existing.wrong_count += 1
                existing.last_wrong_at = datetime.now(timezone.utc)
            else:
                db.add(
                    WrongQuestion(
                        user_id=user.id,
                        question_id=q.id,
                        quiz_set_id=quiz_id,
                    )
                )
        skill_results.setdefault(q.micro_skill, []).append(ok_flag)
        details.append(
            {
                "question_id": q.id,
                "correct": ok_flag,
                "user_answer": ua,
                "answer": q.answer,
                "explanation": q.explanation,
                "micro_skill": q.micro_skill,
            }
        )
    skill_bool = {k: all(v) if v else False for k, v in skill_results.items()}
    # more useful: majority per skill
    skill_bool = {k: (sum(v) / len(v) >= 0.6) for k, v in skill_results.items() if v}
    import json

    mastery: dict = {}
    try:
        redis = get_redis()
        raw = await redis.get(f"mastery:{user.id}")
        mastery = json.loads(raw) if raw else {}
        mastery = apply_play(mastery, skill_bool)
        await redis.set(f"mastery:{user.id}", json.dumps(mastery), ex=60 * 60 * 24 * 90)
    except Exception:
        mastery = apply_play({}, skill_bool)
    rec = PlayRecord(
        user_id=user.id,
        quiz_set_id=quiz_id,
        answers=body.answers,
        skill_results={k: sum(v) / len(v) for k, v in skill_results.items() if v},
        score=round(100.0 * correct_n / len(questions), 1),
        time_spent=body.time_spent,
        mode=body.mode,
    )
    db.add(rec)
    quiz.plays += 1
    await db.commit()
    await db.refresh(rec)
    weak = [k for k, v in rec.skill_results.items() if v < 0.6]
    return ok(
        {
            "record_id": rec.id,
            "score": rec.score,
            "correct": correct_n,
            "total": len(questions),
            "details": details,
            "skill_results": rec.skill_results,
            "weak_skills": weak,
            "next_difficulty": {
                s: recommend_difficulty(mastery, s) for s in skill_results
            },
            "mastery": mastery,
        }
    )


@router.get("/plays")
async def my_plays(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(PlayRecord)
        .where(PlayRecord.user_id == user.id)
        .order_by(PlayRecord.created_at.desc())
        .limit(50)
    )
    items = []
    for r in rows.scalars().all():
        quiz = await db.get(QuizSet, r.quiz_set_id)
        items.append(
            {
                "id": r.id,
                "quiz_id": r.quiz_set_id,
                "title": quiz.title if quiz else "",
                "score": r.score,
                "time_spent": r.time_spent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return ok(items)


@router.get("/wrong-questions")
async def wrong_questions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(WrongQuestion)
        .where(WrongQuestion.user_id == user.id)
        .order_by(WrongQuestion.is_starred.desc(), WrongQuestion.last_wrong_at.desc())
    )
    out = []
    for w in rows.scalars().all():
        q = await db.get(Question, w.question_id)
        if not q:
            continue
        out.append(
            {
                "wrong_count": w.wrong_count,
                "is_starred": bool(w.is_starred),
                "last_wrong_at": w.last_wrong_at.isoformat() if w.last_wrong_at else None,
                "question": {
                    "id": q.id,
                    "content": q.content,
                    "type": q.type,
                    "options": q.options,
                    "micro_skill": q.micro_skill,
                    "quiz_set_id": q.quiz_set_id,
                },
            }
        )
    return ok(out)


@router.delete("/wrong-questions/{question_id}")
async def delete_wrong_question(
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WrongQuestion, (user.id, question_id))
    if not row:
        raise AppError("错题不存在", code=404, status_code=404)
    await db.delete(row)
    await db.commit()
    return ok({"deleted": True})


@router.post("/wrong-questions/{question_id}/star")
async def toggle_wrong_star(
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WrongQuestion, (user.id, question_id))
    if not row:
        raise AppError("错题不存在", code=404, status_code=404)
    row.is_starred = not bool(row.is_starred)
    await db.commit()
    return ok({"is_starred": bool(row.is_starred)})

import hashlib
import json
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
from app.models.question_favorite import QuestionFavorite
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.models.wrong_question import WrongQuestion
from app.schemas.quiz import PlayAnswerUpdateIn, PlaySubmitIn
from app.services.knowledge_tracing import apply_play, recommend_difficulty
from app.services.quality_gates import is_practice_eligible
from app.services.subjective_grading import grade_constructed_response, normalize_answer

router = APIRouter(tags=["practice"])
_AI_GRADABLE_TYPES = {"fill_blank", "application", "proof", "short_answer"}


def _is_correct(question: Question, user_answer) -> bool:
    answer = question.answer or {}
    if question.type == "fill_blank":
        texts = [str(t).strip().lower() for t in (answer.get("texts") or [])]
        return str(user_answer or "").strip().lower() in texts
    keys = [str(k) for k in (answer.get("keys") or [])]
    if isinstance(user_answer, list):
        return sorted(map(str, user_answer)) == sorted(keys)
    return str(user_answer) in keys


def _requires_ai_grading(question: Question) -> bool:
    return question.type in _AI_GRADABLE_TYPES and bool(question.subparts)


def _answer_fingerprint(answer: object) -> str:
    raw = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fill_exact_match(question: Question, user_answer: object) -> bool:
    if question.type != "fill_blank":
        return False
    if not question.subparts:
        return _is_correct(question, user_answer)
    submitted = normalize_answer(_question_payload(question), user_answer)
    expected = {
        str(part.get("id")): {
            str(text).strip().lower() for text in part.get("texts") or [] if str(text).strip()
        }
        for part in (question.answer or {}).get("subparts") or []
        if isinstance(part, dict)
    }
    return bool(expected) and all(
        str(submitted.get(part_id) or "").strip().lower() in texts for part_id, texts in expected.items()
    )


def _question_payload(question: Question) -> dict:
    return {
        "id": question.id,
        "type": question.type,
        "content": question.content,
        "answer": question.answer,
        "subparts": question.subparts,
        "external_sources": question.external_sources,
    }


def _practice_gate_payload(question: Question) -> dict:
    return {
        "type": question.type,
        "options": question.options,
        "answer": question.answer,
        "subparts": question.subparts,
        "needs_review": question.needs_review,
    }


def _is_practice_question(question: Question) -> bool:
    return is_practice_eligible(_practice_gate_payload(question))


def _practice_questions(questions: list[Question]) -> list[Question]:
    return [question for question in questions if _is_practice_question(question)]


def _score_summary(questions: list[Question], answers: dict, ai_grades: dict) -> dict:
    percentages: list[float] = []
    pending = 0
    correct = 0
    for question in questions:
        if _requires_ai_grading(question):
            grade = ai_grades.get(question.id) or {}
            if grade.get("status") != "graded":
                pending += 1
                continue
            percent = float(grade.get("percent") or 0)
            percentages.append(percent)
            if percent >= 60:
                correct += 1
            continue
        ok_flag = _is_correct(question, answers.get(question.id))
        percentages.append(100.0 if ok_flag else 0.0)
        if ok_flag:
            correct += 1
    return {
        "score": round(sum(percentages) / len(percentages), 1) if percentages else 0.0,
        "graded_total": len(percentages),
        "pending_ai_grading": pending,
        "correct": correct,
    }


async def _add_wrong_question(
    db: AsyncSession, user_id: str, question: Question, quiz_id: str, *, increment: bool
) -> None:
    existing = await db.get(WrongQuestion, (user_id, question.id))
    if existing:
        if increment:
            existing.wrong_count += 1
            existing.last_wrong_at = datetime.now(timezone.utc)
        return
    db.add(WrongQuestion(user_id=user_id, question_id=question.id, quiz_set_id=quiz_id))


async def _play_question_details(db: AsyncSession, rec: PlayRecord) -> list[dict]:
    answer_map = rec.answers if isinstance(rec.answers, dict) else {}
    ai_grades = rec.ai_grades if isinstance(rec.ai_grades, dict) else {}
    rows = await db.execute(select(Question).where(Question.quiz_set_id == rec.quiz_set_id))
    questions = list(rows.scalars().all())
    by_id = {q.id: q for q in questions}
    ordered_ids: list[str] = []
    seen: set[str] = set()
    if rec.mode == "wrong_retry":
        for qid in answer_map:
            if qid not in seen:
                ordered_ids.append(str(qid))
                seen.add(str(qid))
    else:
        for q in _practice_questions(questions):
            ordered_ids.append(q.id)
            seen.add(q.id)
        for qid in answer_map:
            sid = str(qid)
            if sid in seen:
                continue
            existing = by_id.get(sid)
            if existing is None or _is_practice_question(existing):
                ordered_ids.append(sid)
                seen.add(sid)
    details: list[dict] = []
    for qid in ordered_ids:
        q = by_id.get(qid)
        ua = answer_map.get(qid)
        if q is None:
            details.append(
                {
                    "question_id": qid,
                    "missing": True,
                    "content": "该题目已不存在",
                    "type": None,
                    "options": None,
                    "user_answer": ua,
                    "answer": None,
                    "correct": False,
                    "explanation": None,
                    "micro_skill": None,
                }
            )
            continue
        details.append(
            {
                "question_id": q.id,
                "missing": False,
                "content": q.content,
                "type": q.type,
                "options": q.options,
                "user_answer": ua,
                "answer": q.answer,
                "correct": (
                    (float((ai_grades.get(q.id) or {}).get("percent") or 0) >= 60)
                    if (ai_grades.get(q.id) or {}).get("status") == "graded"
                    else (None if _requires_ai_grading(q) else _is_correct(q, ua))
                ),
                "explanation": q.explanation,
                "micro_skill": q.micro_skill,
                "subparts": q.subparts,
                "external_sources": q.external_sources,
                "ai_grade": ai_grades.get(q.id),
            }
        )
    return details


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
    questions = _practice_questions(questions)
    if not questions:
        raise AppError("没有可练习的题目")
    details = []
    skill_results: dict[str, list[bool]] = {}
    ai_grades: dict[str, dict] = {}
    for q in questions:
        ua = body.answers.get(q.id)
        if _requires_ai_grading(q):
            normalized = normalize_answer(_question_payload(q), ua)
            ai_grades[q.id] = {
                "status": "pending",
                "answer_hash": _answer_fingerprint(normalized),
                "prompt_version": "grade_constructed_response:v1",
                "exact_match": _fill_exact_match(q, ua) if q.type == "fill_blank" else None,
            }
            details.append(
                {
                    "question_id": q.id,
                    "correct": None,
                    "grading_status": "pending",
                    "user_answer": ua,
                    "answer": q.answer,
                    "explanation": q.explanation,
                    "micro_skill": q.micro_skill,
                }
            )
            continue
        ok_flag = _is_correct(q, ua)
        if not ok_flag:
            await _add_wrong_question(db, user.id, q, quiz_id, increment=True)
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
    skill_bool = {k: (sum(v) / len(v) >= 0.6) for k, v in skill_results.items() if v}

    mastery: dict = {}
    try:
        redis = get_redis()
        raw = await redis.get(f"mastery:{user.id}")
        mastery = json.loads(raw) if raw else {}
        mastery = apply_play(mastery, skill_bool)
        await redis.set(f"mastery:{user.id}", json.dumps(mastery), ex=60 * 60 * 24 * 90)
    except Exception:
        mastery = apply_play({}, skill_bool)
    score_summary = _score_summary(questions, body.answers, ai_grades)
    rec = PlayRecord(
        user_id=user.id,
        quiz_set_id=quiz_id,
        answers=body.answers,
        ai_grades=ai_grades,
        skill_results={k: sum(v) / len(v) for k, v in skill_results.items() if v},
        score=score_summary["score"],
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
            "correct": score_summary["correct"],
            "total": len(questions),
            "graded_total": score_summary["graded_total"],
            "pending_ai_grading": score_summary["pending_ai_grading"],
            "details": details,
            "skill_results": rec.skill_results,
            "weak_skills": weak,
            "next_difficulty": {
                s: recommend_difficulty(mastery, s) for s in skill_results
            },
            "mastery": mastery,
        }
    )


@router.patch("/plays/{play_id}/questions/{question_id}/answer")
async def update_constructed_answer(
    play_id: str,
    question_id: str,
    body: PlayAnswerUpdateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PlayRecord, play_id)
    if not rec or rec.user_id != user.id:
        raise AppError("练习记录不存在", code=404, status_code=404)
    question = await db.get(Question, question_id)
    if not question or question.quiz_set_id != rec.quiz_set_id or not _requires_ai_grading(question):
        raise AppError("主观题不存在或不支持 AI 批改", code=404, status_code=404)
    normalized = normalize_answer(_question_payload(question), body.answer)
    if not any(normalized.values()):
        raise AppError("请先完成至少一个小问", code=400)
    answers = dict(rec.answers or {})
    answers[question_id] = normalized
    grades = dict(rec.ai_grades or {})
    grades[question_id] = {
        "status": "pending",
        "answer_hash": _answer_fingerprint(normalized),
        "prompt_version": "grade_constructed_response:v1",
        "exact_match": _fill_exact_match(question, normalized)
        if question.type == "fill_blank"
        else None,
    }
    rows = await db.execute(select(Question).where(Question.quiz_set_id == rec.quiz_set_id))
    questions = _practice_questions(list(rows.scalars().all()))
    rec.answers = answers
    rec.ai_grades = grades
    rec.score = _score_summary(questions, answers, grades)["score"]
    await db.commit()
    return ok({"question_id": question_id, "grading_status": "pending", "score": rec.score})


@router.post("/plays/{play_id}/questions/{question_id}/ai-grade")
async def grade_play_question(
    play_id: str,
    question_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PlayRecord, play_id)
    if not rec or rec.user_id != user.id:
        raise AppError("练习记录不存在", code=404, status_code=404)
    question = await db.get(Question, question_id)
    if not question or question.quiz_set_id != rec.quiz_set_id or not _requires_ai_grading(question):
        raise AppError("主观题不存在或不支持 AI 批改", code=404, status_code=404)
    answers = dict(rec.answers or {})
    normalized = normalize_answer(_question_payload(question), answers.get(question_id))
    if not any(normalized.values()):
        raise AppError("请先完成至少一个小问", code=400)
    answer_hash = _answer_fingerprint(normalized)
    grades = dict(rec.ai_grades or {})
    previous = grades.get(question_id) or {}
    if previous.get("status") == "graded" and previous.get("answer_hash") == answer_hash:
        return ok({"grade": previous, "score": rec.score, "cached": True})

    quiz = await db.get(QuizSet, rec.quiz_set_id)
    grade = await grade_constructed_response(
        _question_payload(question),
        normalized,
        subject=quiz.subject if quiz else "general",
    )
    grade["answer_hash"] = answer_hash
    grade["prompt_version"] = "grade_constructed_response:v1"
    grade["graded_at"] = datetime.now(timezone.utc).isoformat()
    grades[question_id] = grade
    rows = await db.execute(select(Question).where(Question.quiz_set_id == rec.quiz_set_id))
    questions = _practice_questions(list(rows.scalars().all()))
    score_summary = _score_summary(questions, answers, grades)
    rec.ai_grades = grades
    rec.score = score_summary["score"]
    if grade["status"] == "graded":
        passed = float(grade.get("percent") or 0) >= 60
        if not passed:
            await _add_wrong_question(db, user.id, question, rec.quiz_set_id, increment=False)
        if previous.get("status") != "graded":
            updated_skills = dict(rec.skill_results or {})
            updated_skills[question.micro_skill] = 1.0 if passed else 0.0
            rec.skill_results = updated_skills
            try:
                redis = get_redis()
                raw = await redis.get(f"mastery:{user.id}")
                mastery = json.loads(raw) if raw else {}
                mastery = apply_play(mastery, {question.micro_skill: passed})
                await redis.set(f"mastery:{user.id}", json.dumps(mastery), ex=60 * 60 * 24 * 90)
            except Exception:
                pass
    await db.commit()
    return ok(
        {
            "grade": grade,
            "score": rec.score,
            "graded_total": score_summary["graded_total"],
            "pending_ai_grading": score_summary["pending_ai_grading"],
            "cached": False,
        }
    )


@router.get("/plays")
async def my_plays(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(PlayRecord, QuizSet)
        .outerjoin(QuizSet, QuizSet.id == PlayRecord.quiz_set_id)
        .where(PlayRecord.user_id == user.id)
        .order_by(PlayRecord.created_at.desc())
        .limit(50)
    )
    items = []
    for r, quiz in rows.all():
        items.append(
            {
                "id": r.id,
                "quiz_id": r.quiz_set_id,
                "title": quiz.title if quiz else "",
                "score": r.score,
                "time_spent": r.time_spent,
                "mode": r.mode,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return ok(items)


@router.get("/plays/{play_id}")
async def play_detail(
    play_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PlayRecord, play_id)
    if not rec or rec.user_id != user.id:
        raise AppError("练习记录不存在", code=404, status_code=404)
    quiz = await db.get(QuizSet, rec.quiz_set_id)
    details = await _play_question_details(db, rec)
    correct_n = sum(1 for d in details if d.get("correct"))
    pending_ai_grading = sum(
        1 for detail in details if (detail.get("ai_grade") or {}).get("status") == "pending"
    )
    graded_total = sum(1 for detail in details if detail.get("correct") is not None)
    payload = {
        "id": rec.id,
        "quiz_id": rec.quiz_set_id,
        "title": quiz.title if quiz else "",
        "score": rec.score,
        "time_spent": rec.time_spent,
        "mode": rec.mode,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "skill_results": rec.skill_results or {},
        "correct": correct_n,
        "total": len(details),
        "graded_total": graded_total,
        "pending_ai_grading": pending_ai_grading,
        "details": details,
    }
    return ok(payload)


@router.delete("/plays/{play_id}")
async def delete_play(
    play_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rec = await db.get(PlayRecord, play_id)
    if not rec or rec.user_id != user.id:
        raise AppError("练习记录不存在", code=404, status_code=404)
    await db.delete(rec)
    await db.commit()
    return ok({"deleted": True})


@router.get("/wrong-questions")
async def wrong_questions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(WrongQuestion, Question, QuizSet)
        .join(Question, Question.id == WrongQuestion.question_id)
        .outerjoin(QuizSet, QuizSet.id == WrongQuestion.quiz_set_id)
        .where(WrongQuestion.user_id == user.id)
        .order_by(WrongQuestion.last_wrong_at.desc())
    )
    fav_rows = await db.execute(
        select(QuestionFavorite.question_id).where(QuestionFavorite.user_id == user.id)
    )
    fav_ids = set(fav_rows.scalars().all())
    out = []
    for w, q, quiz in rows.all():
        out.append(
            {
                "wrong_count": w.wrong_count,
                "favorited": w.question_id in fav_ids,
                "last_wrong_at": w.last_wrong_at.isoformat() if w.last_wrong_at else None,
                "quiz": {
                    "id": quiz.id if quiz else q.quiz_set_id,
                    "title": quiz.title if quiz else "未知题库",
                    "category": quiz.category if quiz else "",
                },
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


@router.get("/question-favorites")
async def question_favorites(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(QuestionFavorite, Question, QuizSet)
        .join(Question, Question.id == QuestionFavorite.question_id)
        .outerjoin(QuizSet, QuizSet.id == QuestionFavorite.quiz_set_id)
        .where(QuestionFavorite.user_id == user.id)
        .order_by(QuestionFavorite.created_at.desc())
    )
    out = []
    for fav, q, quiz in rows.all():
        out.append(
            {
                "favorited": True,
                "created_at": fav.created_at.isoformat() if fav.created_at else None,
                "quiz": {
                    "id": quiz.id if quiz else q.quiz_set_id,
                    "title": quiz.title if quiz else "未知题库",
                    "category": quiz.category if quiz else "",
                },
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

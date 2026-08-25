import asyncio
import re
from io import BytesIO

from fastapi import APIRouter, Depends, Response
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.acl import assert_quiz_accessible
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.user import User

router = APIRouter(prefix="/export", tags=["export"])


def _safe_filename(title: str, suffix: str) -> str:
    stem = re.sub(r"[^\w\u4e00-\u9fff\-]+", "_", title).strip("._")[:80] or "quiz"
    return f"{stem}{suffix}"


async def _owned_quiz(db, quiz_id: str, user: User) -> tuple[QuizSet, list[Question]]:
    quiz = await db.get(QuizSet, quiz_id)
    assert_quiz_accessible(quiz, user)
    rows = await db.execute(select(Question).where(Question.quiz_set_id == quiz.id))
    return quiz, list(rows.scalars().all())


def _rows(questions: list[Question]) -> list[dict]:
    out = []
    for q in questions:
        opts = q.options or []
        out.append(
            {
                "id": q.id,
                "type": q.type,
                "stem": q.content,
                "options": opts,
                "answer": q.answer,
                "explanation": q.explanation,
                "difficulty": q.difficulty,
                "micro_skill": q.micro_skill,
                "knowledge_tags": q.knowledge_tags,
                "needs_review": q.needs_review,
            }
        )
    return out


@router.get("/{quiz_id}.json")
async def export_json(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz, questions = await _owned_quiz(db, quiz_id, user)
    import json

    payload = {
        "id": quiz.id,
        "title": quiz.title,
        "category": quiz.category,
        "subject": quiz.subject,
        "questions": _rows(questions),
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=data,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(quiz.title, ".json")}"'},
    )


@router.get("/{quiz_id}.xlsx")
async def export_xlsx(
    quiz_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    quiz, questions = await _owned_quiz(db, quiz_id, user)
    wb = Workbook()
    ws = wb.active
    ws.title = "questions"
    ws.append(["题干", "类型", "选项", "答案", "解析", "难度", "微技能", "待审校"])
    for q in questions:
        opts = " | ".join(f"{o.get('key')}. {o.get('text')}" for o in (q.options or []))
        ws.append(
            [
                q.content,
                q.type,
                opts,
                str(q.answer),
                q.explanation or "",
                q.difficulty,
                q.micro_skill,
                "是" if q.needs_review else "否",
            ]
        )
    buf = BytesIO()
    await asyncio.to_thread(wb.save, buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(quiz.title, ".xlsx")}"'},
    )

import pytest
from sqlalchemy import select

from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.wrong_question import WrongQuestion
from tests.conftest import register


async def _subjective_quiz(client, session_factory):
    registered = await register(client, "ai-grade@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(creator_id=user_id, title="主观题练习", status="ready", visibility="private")
        db.add(quiz)
        await db.flush()
        question = Question(
            quiz_set_id=quiz.id,
            type="short_answer",
            content="说明光合作用的主要场所。",
            answer={"subparts": [{"id": "p1", "expected_points": ["叶绿体"]}]},
            subparts=[
                {
                    "id": "p1",
                    "prompt": "写出主要场所并说明理由。",
                    "rubric": {
                        "max_score": 5,
                        "criteria": [{"description": "写出叶绿体", "points": 5}],
                    },
                }
            ],
            source_span={"quote": "光合作用发生在叶绿体中。"},
            micro_skill="detail",
        )
        db.add(question)
        await db.commit()
        return token, user_id, quiz.id, question.id


@pytest.mark.asyncio
async def test_subjective_answer_stays_pending_until_ai_grade(client, session_factory, monkeypatch):
    token, user_id, quiz_id, question_id = await _subjective_quiz(client, session_factory)
    headers = {"Authorization": f"Bearer {token}"}
    submitted = await client.post(
        f"/api/plays/{quiz_id}",
        headers=headers,
        json={"answers": {question_id: {"p1": "叶绿体，因为它含叶绿素"}}, "time_spent": 3},
    )
    assert submitted.status_code == 200
    payload = submitted.json()["data"]
    assert payload["pending_ai_grading"] == 1
    assert payload["graded_total"] == 0

    async with session_factory() as db:
        wrong = await db.scalar(select(WrongQuestion).where(WrongQuestion.user_id == user_id))
        assert wrong is None

    async def _grade(*_args, **_kwargs):
        return {
            "status": "graded",
            "subparts": [
                {
                    "id": "p1",
                    "score": 5,
                    "max_score": 5,
                    "evidence": "满足得分点",
                    "feedback": "答案完整",
                }
            ],
            "score": 5,
            "max_score": 5,
            "percent": 100.0,
            "overall_feedback": "很好",
            "provider": "mock",
            "model": "mock-local",
        }

    monkeypatch.setattr("app.api.plays.grade_constructed_response", _grade)
    graded = await client.post(
        f"/api/plays/{payload['record_id']}/questions/{question_id}/ai-grade",
        headers=headers,
    )
    assert graded.status_code == 200
    assert graded.json()["data"]["score"] == 100.0
    assert graded.json()["data"]["pending_ai_grading"] == 0

    cached = await client.post(
        f"/api/plays/{payload['record_id']}/questions/{question_id}/ai-grade",
        headers=headers,
    )
    assert cached.status_code == 200
    assert cached.json()["data"]["cached"] is True

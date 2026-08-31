import pytest

from app.models.document import Document
from app.models.question import Question
from app.models.quiz_set import QuizSet
from tests.conftest import register


async def _noop_generation(_job_id: str) -> None:
    return None


@pytest.mark.asyncio
async def test_generate_creates_quiz_as_generating(client, session_factory, monkeypatch):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)
    registered = await register(client, "gen-status@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="lesson.md",
            content_type="text/markdown",
            object_key="lesson.md",
            size_bytes=12,
            status="parsed",
            extracted_text="叶绿体进行光合作用。",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    created = await client.post(
        "/api/quizzes/generate",
        headers=headers,
        json={"document_id": doc_id, "title": "进行中的题库", "blueprint": {"total_questions": 8}},
    )
    assert created.status_code == 200, created.text
    quiz_id = created.json()["data"]["quiz_id"]

    listed = await client.get("/api/quizzes", headers=headers)
    assert listed.status_code == 200
    row = next(item for item in listed.json()["data"] if item["id"] == quiz_id)
    assert row["status"] == "generating"
    assert row["generation_job_id"]
    assert row["blueprint"]["total_questions"] == 8

    detail = await client.get(f"/api/quizzes/{quiz_id}?purpose=review", headers=headers)
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["status"] == "generating"
    assert body["questions"] == []


@pytest.mark.asyncio
async def test_draft_quiz_with_questions_is_visible_without_stale_zero_count(client, session_factory):
    registered = await register(client, "draft-visible@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(
            creator_id=user_id,
            title="已出完但仍是草稿",
            status="draft",
            visibility="private",
            question_count=0,
            blueprint={"total_questions": 8},
        )
        db.add(quiz)
        await db.flush()
        db.add(
            Question(
                quiz_set_id=quiz.id,
                type="single_choice",
                content="光合作用发生在哪里？",
                options=[
                    {"key": "A", "text": "叶绿体"},
                    {"key": "B", "text": "线粒体"},
                    {"key": "C", "text": "核糖体"},
                    {"key": "D", "text": "高尔基体"},
                ],
                answer={"keys": ["A"], "texts": ["叶绿体"]},
                micro_skill="detail",
                needs_review=False,
            )
        )
        await db.commit()
        quiz_id = quiz.id

    listed = await client.get("/api/quizzes", headers=headers)
    assert listed.status_code == 200
    row = next(item for item in listed.json()["data"] if item["id"] == quiz_id)
    assert row["question_count"] == 1

    review = await client.get(f"/api/quizzes/{quiz_id}?purpose=review", headers=headers)
    assert review.status_code == 200
    data = review.json()["data"]
    assert [question["content"] for question in data["questions"]] == ["光合作用发生在哪里？"]
    assert data["question_count"] == 1

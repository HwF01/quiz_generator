import pytest

from sqlalchemy import select

from app.models.document import Document
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.wrong_question import WrongQuestion
from tests.conftest import register


async def _quiz_with_questions(client, session_factory):
    registered = await register(client, "review@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(creator_id=user_id, title="审校题库", status="ready", visibility="private")
        db.add(quiz)
        await db.flush()
        ready = Question(
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
            quality_scores={},
            needs_review=False,
        )
        pending = Question(
            quiz_set_id=quiz.id,
            type="single_choice",
            content="待补干扰项的题干",
            options=None,
            answer={"texts": ["正解"]},
            micro_skill="detail",
            quality_scores={"review_reasons": ["distractors_insufficient"]},
            needs_review=True,
        )
        db.add_all([ready, pending])
        await db.commit()
        return token, quiz.id, pending.id


@pytest.mark.asyncio
async def test_practice_hides_pending_questions(client, session_factory):
    token, quiz_id, _ = await _quiz_with_questions(client, session_factory)
    headers = {"Authorization": f"Bearer {token}"}

    practice = await client.get(f"/api/quizzes/{quiz_id}?purpose=practice", headers=headers)
    review = await client.get(f"/api/quizzes/{quiz_id}?purpose=review", headers=headers)

    assert practice.status_code == 200
    assert [question["content"] for question in practice.json()["data"]["questions"]] == ["光合作用发生在哪里？"]
    assert len(review.json()["data"]["questions"]) == 2


@pytest.mark.asyncio
async def test_practice_submit_excludes_pending_questions(client, session_factory):
    token, quiz_id, pending_id = await _quiz_with_questions(client, session_factory)
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]

    practice = await client.get(f"/api/quizzes/{quiz_id}?purpose=practice", headers=headers)
    ready_id = practice.json()["data"]["questions"][0]["id"]

    submitted = await client.post(
        f"/api/plays/{quiz_id}",
        headers=headers,
        json={"answers": {ready_id: "A"}, "time_spent": 5, "mode": "sequential"},
    )
    assert submitted.status_code == 200
    payload = submitted.json()["data"]
    detail_ids = [item["question_id"] for item in payload["details"]]
    assert payload["total"] == 1
    assert payload["correct"] == 1
    assert payload["score"] == 100.0
    assert detail_ids == [ready_id]
    assert pending_id not in detail_ids

    async with session_factory() as db:
        wrong = await db.scalar(
            select(WrongQuestion).where(
                WrongQuestion.user_id == user_id,
                WrongQuestion.question_id == pending_id,
            )
        )
        assert wrong is None

    detail = await client.get(f"/api/plays/{payload['record_id']}", headers=headers)
    assert detail.status_code == 200
    recorded = detail.json()["data"]
    recorded_ids = [item["question_id"] for item in recorded["details"]]
    assert recorded["total"] == 1
    assert recorded["correct"] == 1
    assert recorded_ids == [ready_id]
    assert pending_id not in recorded_ids
    assert all(item.get("user_answer") is not None for item in recorded["details"])


@pytest.mark.asyncio
async def test_incomplete_choice_cannot_be_marked_reviewed(client, session_factory):
    token, _, question_id = await _quiz_with_questions(client, session_factory)

    response = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"needs_review": False},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "请先补全 4 个不同选项并指定唯一正解，再标记已审"


async def _quiz_with_multi_choice(client, session_factory, *, complete: bool):
    registered = await register(client, "multi-review@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(creator_id=user_id, title="多选题审校", status="ready", visibility="private")
        db.add(quiz)
        await db.flush()
        question = Question(
            quiz_set_id=quiz.id,
            type="multi_choice",
            content="下列哪些是细胞器？",
            options=(
                [
                    {"key": "A", "text": "叶绿体"},
                    {"key": "B", "text": "线粒体"},
                    {"key": "C", "text": "核糖体"},
                    {"key": "D", "text": "高尔基体"},
                ]
                if complete
                else None
            ),
            answer={"keys": ["A"] if not complete else ["A", "B"], "texts": ["叶绿体", "线粒体"]},
            micro_skill="detail",
            quality_scores={},
            needs_review=True,
        )
        db.add(question)
        await db.commit()
        return token, quiz.id, question.id


@pytest.mark.asyncio
async def test_incomplete_multi_choice_cannot_be_marked_reviewed(client, session_factory):
    token, _, question_id = await _quiz_with_multi_choice(client, session_factory, complete=False)

    response = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"needs_review": False},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "请先补全 4 个不同选项并指定至少两个正解，再标记已审"


@pytest.mark.asyncio
async def test_complete_multi_choice_can_be_marked_reviewed(client, session_factory):
    token, _, question_id = await _quiz_with_multi_choice(client, session_factory, complete=True)

    response = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"needs_review": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["needs_review"] is False


@pytest.mark.asyncio
async def test_multi_choice_play_requires_all_correct_keys(client, session_factory):
    token, quiz_id, question_id = await _quiz_with_multi_choice(client, session_factory, complete=True)
    headers = {"Authorization": f"Bearer {token}"}
    reviewed = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers=headers,
        json={"needs_review": False},
    )
    assert reviewed.status_code == 200

    submitted = await client.post(
        f"/api/plays/{quiz_id}",
        headers=headers,
        json={"answers": {question_id: ["A", "B"]}, "time_spent": 5, "mode": "sequential"},
    )
    assert submitted.status_code == 200
    payload = submitted.json()["data"]
    assert payload["correct"] == 1
    assert payload["score"] == 100.0

    partial = await client.post(
        f"/api/plays/{quiz_id}",
        headers=headers,
        json={"answers": {question_id: ["A"]}, "time_spent": 5, "mode": "sequential"},
    )
    assert partial.status_code == 200
    assert partial.json()["data"]["correct"] == 0
    assert partial.json()["data"]["score"] == 0.0


async def _quiz_with_true_false(client, session_factory, *, complete: bool):
    registered = await register(client, "tf-review@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(creator_id=user_id, title="判断题审校", status="ready", visibility="private")
        db.add(quiz)
        await db.flush()
        question = Question(
            quiz_set_id=quiz.id,
            type="true_false",
            content="光合作用主要发生在叶绿体中。",
            options=(
                [
                    {"key": "对", "text": "对"},
                    {"key": "错", "text": "错"},
                ]
                if complete
                else [{"key": "对", "text": "对"}]
            ),
            answer={"keys": ["对"], "texts": ["对"]},
            micro_skill="detail",
            quality_scores={},
            needs_review=True,
        )
        db.add(question)
        await db.commit()
        return token, question.id


@pytest.mark.asyncio
async def test_complete_true_false_can_be_marked_reviewed(client, session_factory):
    token, question_id = await _quiz_with_true_false(client, session_factory, complete=True)

    response = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"needs_review": False},
    )

    assert response.status_code == 200
    assert response.json()["data"]["needs_review"] is False


@pytest.mark.asyncio
async def test_incomplete_true_false_cannot_be_marked_reviewed(client, session_factory):
    token, question_id = await _quiz_with_true_false(client, session_factory, complete=False)

    response = await client.patch(
        f"/api/quizzes/questions/{question_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"needs_review": False},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "请先补全对/错选项并指定唯一正解，再标记已审"


@pytest.mark.asyncio
async def test_quiz_with_pending_question_cannot_be_published(client, session_factory):
    token, quiz_id, _ = await _quiz_with_questions(client, session_factory)

    response = await client.patch(
        f"/api/quizzes/{quiz_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"visibility": "public"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "题库仍有待审校题目，完成审校后才能公开"


@pytest.mark.asyncio
async def test_harden_uses_full_mapped_passage(client, session_factory, monkeypatch):
    registered = await register(client, "harden@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        document = Document(
            owner_id=user_id,
            filename="lesson.md",
            content_type="text/markdown",
            object_key="lesson.md",
            size_bytes=1,
            status="parsed",
            extracted_text="短原文。",
            passage_map=[{"chunk_id": "c1", "text": "完整篇章：叶绿体进行光合作用，线粒体进行呼吸作用。"}],
        )
        db.add(document)
        await db.flush()
        quiz = QuizSet(creator_id=user_id, document_id=document.id, title="加固题库", status="ready")
        db.add(quiz)
        await db.flush()
        question = Question(
            quiz_set_id=quiz.id,
            type="single_choice",
            content="光合作用发生在哪里？",
            options=None,
            answer={"texts": ["叶绿体"]},
            source_span={"quote": "叶绿体进行光合作用"},
            source_chunk_id="c1",
            micro_skill="detail",
            needs_review=True,
        )
        db.add(question)
        await db.commit()
        question_id = question.id

    captured: list[str] = []

    async def _build(_stem, passage, _chunk_id, **_kwargs):
        captured.append(passage)
        return {
            "options": None,
            "answer": {"texts": ["叶绿体"]},
            "distractor_rationale": None,
            "quality_scores": {"review_reasons": ["distractors_insufficient"]},
            "needs_review": True,
        }

    async def _gates(question, _passage, **_kwargs):
        return question

    monkeypatch.setattr("app.api.quizzes.build_choice_question", _build)
    monkeypatch.setattr("app.api.quizzes.apply_gates", _gates)
    response = await client.post(
        f"/api/quizzes/questions/{question_id}/harden",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert captured == ["完整篇章：叶绿体进行光合作用，线粒体进行呼吸作用。"]

import pytest
from sqlalchemy import select

from app.models.document import Document
from app.models.generation_job import GenerationJob
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.services.pipeline import run_generation
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


async def _seed_parsed_doc(session_factory, user_id: str) -> str:
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
        return doc.id


async def _quota(client, headers) -> dict:
    res = await client.get("/api/stats/quota", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["data"]


@pytest.mark.asyncio
async def test_generation_failure_keeps_failed_draft_and_refunds_quota(
    client, session_factory, monkeypatch
):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)

    async def _boom(*_a, **_k):
        raise RuntimeError("文档中没有适合出题的段落，请检查材料或换一份文档")

    monkeypatch.setattr("app.services.pipeline.prepare_generation_preview", _boom)

    registered = await register(client, "gen-fail-keep@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    doc_id = await _seed_parsed_doc(session_factory, user_id)

    created = await client.post(
        "/api/quizzes/generate",
        headers=headers,
        json={
            "document_id": doc_id,
            "title": "失败后应留下的题库",
            "blueprint": {"total_questions": 6},
        },
    )
    assert created.status_code == 200, created.text
    quiz_id = created.json()["data"]["quiz_id"]
    job_id = created.json()["data"]["job_id"]
    assert (await _quota(client, headers))["used"] == 1

    with pytest.raises(RuntimeError, match="没有适合出题"):
        async with session_factory() as db:
            await run_generation(db, job_id)

    listed = await client.get("/api/quizzes", headers=headers)
    assert listed.status_code == 200
    row = next(item for item in listed.json()["data"] if item["id"] == quiz_id)
    assert row["status"] == "failed"
    assert row["title"] == "失败后应留下的题库"
    assert row["blueprint"]["total_questions"] == 6
    assert row["generation_job_id"] == job_id

    async with session_factory() as db:
        quiz = await db.get(QuizSet, quiz_id)
        job = await db.get(GenerationJob, job_id)
        assert quiz is not None
        assert quiz.status == "failed"
        assert quiz.document_id == doc_id
        assert quiz.title == "失败后应留下的题库"
        assert quiz.generation_job_id == job_id
        assert job is not None
        assert job.status == "failed"
        assert job.quiz_set_id == quiz_id

    assert (await _quota(client, headers))["used"] == 0


@pytest.mark.asyncio
async def test_retry_failed_quiz_reuses_document_and_charges_quota(
    client, session_factory, monkeypatch
):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)
    registered = await register(client, "gen-retry@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    doc_id = await _seed_parsed_doc(session_factory, user_id)

    async with session_factory() as db:
        job = GenerationJob(
            user_id=user_id,
            document_id=doc_id,
            status="failed",
            stage="失败",
            error="模型服务暂不可用",
            config={
                "document_id": doc_id,
                "title": "可重试草稿",
                "category": "自定义",
                "subject": "general",
                "visibility": "private",
                "blueprint": {"total_questions": 8},
                "force": False,
            },
        )
        db.add(job)
        await db.flush()
        quiz = QuizSet(
            creator_id=user_id,
            document_id=doc_id,
            generation_job_id=job.id,
            title="可重试草稿",
            status="failed",
            blueprint={"total_questions": 8},
        )
        db.add(quiz)
        await db.flush()
        job.quiz_set_id = quiz.id
        db.add(
            Question(
                quiz_set_id=quiz.id,
                type="single_choice",
                content="残留题",
                options=[{"key": "A", "text": "1"}],
                answer={"keys": ["A"]},
                micro_skill="detail",
            )
        )
        quiz.question_count = 1
        await db.commit()
        quiz_id = quiz.id
        old_job_id = job.id

    retried = await client.post(f"/api/quizzes/{quiz_id}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    data = retried.json()["data"]
    assert data["quiz_id"] == quiz_id
    assert data["job_id"] != old_job_id
    assert (await _quota(client, headers))["used"] == 1

    listed = await client.get("/api/quizzes", headers=headers)
    row = next(item for item in listed.json()["data"] if item["id"] == quiz_id)
    assert row["status"] == "generating"
    assert row["generation_job_id"] == data["job_id"]
    assert row["title"] == "可重试草稿"
    assert row["blueprint"]["total_questions"] == 8

    detail = await client.get(f"/api/quizzes/{quiz_id}?purpose=review", headers=headers)
    assert detail.json()["data"]["questions"] == []

    async with session_factory() as db:
        quiz = await db.get(QuizSet, quiz_id)
        assert quiz.document_id == doc_id
        leftover = (
            await db.execute(select(Question.id).where(Question.quiz_set_id == quiz_id))
        ).scalars().all()
        assert leftover == []


@pytest.mark.asyncio
async def test_retry_rejects_non_failed_missing_document_and_other_users(
    client, session_factory, monkeypatch
):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)
    owner = await register(client, "retry-owner@example.com")
    other = await register(client, "retry-other@example.com")
    owner_headers = {"Authorization": f"Bearer {owner['token']}"}
    other_headers = {"Authorization": f"Bearer {other['token']}"}
    me = await client.get("/api/auth/me", headers=owner_headers)
    user_id = me.json()["data"]["id"]
    doc_id = await _seed_parsed_doc(session_factory, user_id)

    async with session_factory() as db:
        ready = QuizSet(creator_id=user_id, document_id=doc_id, title="已完成", status="ready")
        orphan = QuizSet(creator_id=user_id, title="无文档失败", status="failed")
        failed = QuizSet(
            creator_id=user_id,
            document_id=doc_id,
            title="失败草稿",
            status="failed",
            blueprint={"total_questions": 4},
        )
        db.add_all([ready, orphan, failed])
        await db.commit()
        ready_id, orphan_id, failed_id = ready.id, orphan.id, failed.id

    not_failed = await client.post(f"/api/quizzes/{ready_id}/retry", headers=owner_headers)
    assert not_failed.status_code == 400
    assert "失败" in not_failed.json()["message"]

    no_doc = await client.post(f"/api/quizzes/{orphan_id}/retry", headers=owner_headers)
    assert no_doc.status_code == 404
    assert "文档" in no_doc.json()["message"]

    foreign = await client.post(f"/api/quizzes/{failed_id}/retry", headers=other_headers)
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_failure_keeps_failed_draft(client, session_factory, monkeypatch):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)
    monkeypatch.setattr(
        "app.api.quizzes.settings",
        type("S", (), {"is_local_stack": False, "web_search_available": False})(),
    )

    async def _boom(*_a, **_k):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.api.quizzes.create_pool", _boom)

    registered = await register(client, "enqueue-fail@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    doc_id = await _seed_parsed_doc(session_factory, user_id)

    created = await client.post(
        "/api/quizzes/generate",
        headers=headers,
        json={"document_id": doc_id, "title": "队列失败草稿", "blueprint": {"total_questions": 4}},
    )
    assert created.status_code == 503
    body = created.json()
    assert body["message"] == "任务队列暂不可用，请稍后重试"
    assert (await _quota(client, headers))["used"] == 0

    listed = await client.get("/api/quizzes", headers=headers)
    titles = [item["title"] for item in listed.json()["data"]]
    assert "队列失败草稿" in titles
    row = next(item for item in listed.json()["data"] if item["title"] == "队列失败草稿")
    assert row["status"] == "failed"
    assert body["data"]["quiz_id"] == row["id"]
    assert body["data"]["job_id"] == row["generation_job_id"]

    async with session_factory() as db:
        quiz = (
            await db.execute(select(QuizSet).where(QuizSet.creator_id == user_id, QuizSet.title == "队列失败草稿"))
        ).scalar_one()
        assert quiz.document_id == doc_id
        assert quiz.status == "failed"

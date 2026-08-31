import pytest
from sqlalchemy import select

from app.models.document import Document
from app.models.generation_job import GenerationJob
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.services.cache import content_hash
from app.services.pipeline import run_generation
from app.services.quiz_generator import generate_stem as real_generate_stem
from tests.conftest import register

PHOTOSYNTHESIS = (
    "光合作用是绿色植物利用光能把二氧化碳和水转化成有机物并释放氧气的过程。"
    "叶绿体是光合作用的主要场所。"
    "光反应发生在类囊体膜上，暗反应在叶绿体基质中进行。"
)

SHORT_KEYS = "叶绿体是光合作用的主要场所。光反应发生在类囊体膜上。"


async def _user_id(client, email: str) -> str:
    data = await register(client, email)
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    return me.json()["data"]["id"]


async def _seed_job(
    session_factory,
    user_id: str,
    text: str,
    *,
    title: str,
    blueprint: dict | None = None,
) -> tuple[str, str]:
    extracted = text
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="lesson.md",
            content_type="text/markdown",
            object_key="lesson.md",
            size_bytes=len(extracted.encode("utf-8")),
            status="parsed",
            extracted_text=extracted,
            extracted_chars=len(extracted),
            content_hash=content_hash(extracted),
        )
        db.add(doc)
        await db.flush()
        job = GenerationJob(
            user_id=user_id,
            document_id=doc.id,
            status="queued",
            stage="queued",
            config={
                "document_id": doc.id,
                "title": title,
                "blueprint": blueprint or {"total_questions": 8},
            },
        )
        db.add(job)
        await db.flush()
        quiz = QuizSet(
            creator_id=user_id,
            document_id=doc.id,
            generation_job_id=job.id,
            title=title,
            status="generating",
            visibility="private",
            blueprint=blueprint or {"total_questions": 8},
        )
        db.add(quiz)
        await db.flush()
        job.quiz_set_id = quiz.id
        await db.commit()
        return job.id, quiz.id


async def test_generation_reuses_cached_quiz_for_same_owner_hash_config(
    client, session_factory, fake_redis
):
    user_id = await _user_id(client, "pipeline-cache@example.com")
    first_job_id, source_quiz_id = await _seed_job(
        session_factory, user_id, PHOTOSYNTHESIS, title="源题库"
    )
    async with session_factory() as db:
        await run_generation(db, first_job_id)

    async with session_factory() as db:
        source = await db.get(QuizSet, source_quiz_id)
        assert source is not None
        assert source.status == "ready"
        source_contents = list(
            (
                await db.execute(
                    select(Question.content).where(Question.quiz_set_id == source_quiz_id)
                )
            ).scalars().all()
        )
        assert source_contents

    dest_job_id, dest_quiz_id = await _seed_job(
        session_factory, user_id, PHOTOSYNTHESIS, title="复用题库"
    )
    async with session_factory() as db:
        await run_generation(db, dest_job_id)

    async with session_factory() as db:
        dest = await db.get(QuizSet, dest_quiz_id)
        job = await db.get(GenerationJob, dest_job_id)
        dest_contents = list(
            (
                await db.execute(
                    select(Question.content).where(Question.quiz_set_id == dest_quiz_id)
                )
            ).scalars().all()
        )
        assert dest is not None
        assert dest.status == "ready"
        assert dest_contents == source_contents
        assert (job.models_used or {}).get("reused_quiz_id") == source_quiz_id


async def test_generation_reduces_count_when_key_sentences_are_short(
    client, session_factory, fake_redis
):
    user_id = await _user_id(client, "pipeline-short@example.com")
    job_id, quiz_id = await _seed_job(
        session_factory,
        user_id,
        SHORT_KEYS,
        title="短关键句",
        blueprint={"total_questions": 8},
    )
    async with session_factory() as db:
        await run_generation(db, job_id)

    async with session_factory() as db:
        quiz = await db.get(QuizSet, quiz_id)
        job = await db.get(GenerationJob, job_id)
        assert quiz is not None
        assert quiz.status == "ready"
        assert quiz.question_count < 8
        assert "可溯源关键句不足" in str((job.models_used or {}).get("shortfall_reason") or "")


async def test_generation_failure_deletes_quiz(client, session_factory, fake_redis):
    user_id = await _user_id(client, "pipeline-fail@example.com")
    job_id, quiz_id = await _seed_job(session_factory, user_id, "短", title="失败应删库")
    async with session_factory() as db:
        with pytest.raises(RuntimeError, match="没有适合出题的段落"):
            await run_generation(db, job_id)

    async with session_factory() as db:
        assert await db.get(QuizSet, quiz_id) is None
        job = await db.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.quiz_set_id is None


async def test_invalid_external_source_marks_needs_review(
    client, session_factory, fake_redis, monkeypatch
):
    async def _stub_search(_queries):
        return [
            {
                "id": "web-known",
                "title": "光合",
                "url": "https://example.test/photo",
                "excerpt": "可靠摘要",
                "query": "general 叶绿体",
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "used": False,
            }
        ]

    async def _stem_with_unknown_source(*args, **kwargs):
        data = await real_generate_stem(*args, **kwargs)
        data["external_source_ids"] = ["web-unknown"]
        return data

    monkeypatch.setattr("app.services.pipeline.search_related_knowledge", _stub_search)
    monkeypatch.setattr("app.services.pipeline.generate_stem", _stem_with_unknown_source)

    user_id = await _user_id(client, "pipeline-source@example.com")
    job_id, quiz_id = await _seed_job(
        session_factory,
        user_id,
        PHOTOSYNTHESIS,
        title="非法来源",
        blueprint={"total_questions": 2, "enable_web_search": True},
    )
    async with session_factory() as db:
        await run_generation(db, job_id)

    async with session_factory() as db:
        questions = (
            await db.execute(select(Question).where(Question.quiz_set_id == quiz_id))
        ).scalars().all()
        assert questions
        assert any(question.needs_review for question in questions)
        reasons = [
            reason
            for question in questions
            for reason in (question.quality_scores or {}).get("review_reasons", [])
        ]
        assert "invalid_external_source" in reasons

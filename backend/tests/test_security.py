from datetime import datetime, timezone

from httpx import AsyncClient

from app.core.acl import SEED_EMAIL
from app.models.play_record import PlayRecord
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.services.quality_gates import answer_exists
from tests.conftest import FakeRedis, register


async def test_private_quiz_play_is_404(client: AsyncClient, session_factory):
    owner_data = await register(client, "owner@example.com")
    other_data = await register(client, "other@example.com")
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {owner_data['token']}"})
    owner_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(
            creator_id=owner_id,
            title="私有",
            visibility="private",
            status="ready",
            question_count=1,
        )
        db.add(quiz)
        await db.flush()
        db.add(
            Question(
                quiz_set_id=quiz.id,
                type="single_choice",
                content="q",
                options=[{"key": "A", "text": "1"}],
                answer={"keys": ["A"]},
                micro_skill="detail",
            )
        )
        await db.commit()
        quiz_id = quiz.id
    res = await client.post(
        f"/api/plays/{quiz_id}",
        headers={"Authorization": f"Bearer {other_data['token']}"},
        json={"answers": {}, "time_spent": 1, "mode": "sequential"},
    )
    assert res.status_code == 404
    assert res.json()["code"] == 404


async def test_seed_email_login_rejected(client: AsyncClient):
    res = await client.post(
        "/api/auth/login",
        json={"email": SEED_EMAIL, "password": "anything123"},
    )
    assert res.status_code == 401
    assert res.json()["code"] == 401


async def test_login_returns_token(client: AsyncClient):
    await register(client, "login-ok@example.com")
    res = await client.post(
        "/api/auth/login",
        json={"email": "login-ok@example.com", "password": "password12"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    assert body["data"]["token"]
    assert body["data"]["user"]["email"] == "login-ok@example.com"


async def test_quota_exhausted_is_429(client: AsyncClient, fake_redis: FakeRedis):
    data = await register(client, "quota@example.com")
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
    user_id = me.json()["data"]["id"]
    key = f"quota:{user_id}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    fake_redis.kv[key] = "20"
    res = await client.post(
        "/api/quizzes/generate",
        headers={"Authorization": f"Bearer {data['token']}"},
        json={"document_id": "00000000-0000-0000-0000-000000000001", "title": "x"},
    )
    assert res.status_code == 429
    assert res.json()["code"] == 429


async def test_redis_down_quota_is_503(client: AsyncClient, fake_redis: FakeRedis):
    data = await register(client, "down@example.com")
    fake_redis.down = True
    res = await client.post(
        "/api/quizzes/generate",
        headers={"Authorization": f"Bearer {data['token']}"},
        json={"document_id": "00000000-0000-0000-0000-000000000001", "title": "x"},
    )
    assert res.status_code == 503
    assert res.json()["code"] == 503


async def test_delete_quiz_with_play_record(client: AsyncClient, session_factory):
    data = await register(client, "del@example.com")
    token = data["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(
            creator_id=user_id,
            title="可删",
            visibility="private",
            status="ready",
            question_count=1,
        )
        db.add(quiz)
        await db.flush()
        db.add(
            Question(
                quiz_set_id=quiz.id,
                type="single_choice",
                content="q",
                options=[{"key": "A", "text": "1"}],
                answer={"keys": ["A"]},
                micro_skill="detail",
            )
        )
        db.add(
            PlayRecord(
                user_id=user_id,
                quiz_set_id=quiz.id,
                answers={},
                score=10,
                time_spent=3,
                mode="sequential",
            )
        )
        await db.commit()
        quiz_id = quiz.id
    res = await client.delete(f"/api/quizzes/{quiz_id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["code"] == 0


def test_answer_exists_unrelated_quote_is_false():
    q = {
        "type": "single_choice",
        "content": "光合作用主要发生在哪里？",
        "options": [{"key": "A", "text": "叶绿体"}, {"key": "B", "text": "线粒体"}],
        "answer": {"keys": ["A"], "texts": ["叶绿体"]},
        "source_span": {"quote": "The capital of France is Paris."},
        "explanation": "与引文无关的解析也不应放行",
    }
    assert answer_exists(q) is False

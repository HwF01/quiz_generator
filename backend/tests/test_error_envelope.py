import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError, TimeoutError as SATimeoutError
from starlette.requests import Request

from app.core.exceptions import AppError, unhandled_error_handler
from app.main import app
from app.models.document import Document
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.services.llm.providers import _post_with_retry
from tests.conftest import register


def _dummy_request(path: str = "/api/_test_unhandled") -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "root_path": "",
            "scheme": "http",
            "query_string": b"",
            "headers": [],
            "client": ("test", 50000),
            "server": ("test", 80),
        }
    )


async def test_unhandled_error_handler_json_body():
    res = await unhandled_error_handler(_dummy_request(), RuntimeError("boom"))
    assert res.status_code == 500
    assert res.body
    body = json.loads(res.body)
    assert body == {"code": 500, "data": None, "message": "服务器繁忙，请稍后重试"}


async def test_unhandled_error_returns_json_envelope(client: AsyncClient):
    @app.get("/api/_test_unhandled")
    async def _boom():
        raise RuntimeError("boom")

    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/_test_unhandled")
        assert res.status_code == 500
        assert "application/json" in res.headers.get("content-type", "")
        body = res.json()
        assert body["code"] == 500
        assert body["data"] is None
        assert body["message"] == "服务器繁忙，请稍后重试"
        assert not res.text.lstrip().startswith("Internal")
    finally:
        app.router.routes[:] = [
            r for r in app.router.routes if getattr(r, "path", None) != "/api/_test_unhandled"
        ]


async def test_upload_storage_failure_is_json(client: AsyncClient, monkeypatch):
    data = await register(client, "uploadfail@example.com")
    token = data["token"]

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("app.api.documents.upload_bytes", boom)
    res = await client.post(
        "/api/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 503
    body = res.json()
    assert body["code"] == 503
    assert body["message"] == "文件保存失败，请稍后重试"


async def test_list_quizzes_includes_failed_drafts_without_deleting(client: AsyncClient, session_factory):
    data = await register(client, "failedlist@example.com")
    token = data["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        db.add(
            QuizSet(
                creator_id=user_id,
                title="坏的",
                status="failed",
                visibility="private",
            )
        )
        db.add(
            QuizSet(
                creator_id=user_id,
                title="好的",
                status="ready",
                visibility="private",
            )
        )
        await db.commit()
    res = await client.get("/api/quizzes", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    titles = [q["title"] for q in res.json()["data"]]
    assert set(titles) == {"坏的", "好的"}
    assert len(titles) == 2
    async with session_factory() as db:
        rows = (
            await db.execute(select(QuizSet.title).where(QuizSet.creator_id == user_id))
        ).scalars().all()
    assert set(rows) == {"坏的", "好的"}


async def test_unhandled_maps_operational_error():
    res = await unhandled_error_handler(
        _dummy_request(),
        OperationalError("SELECT 1", {}, Exception("database is locked")),
    )
    assert res.status_code == 503
    assert json.loads(res.body) == {
        "code": 503,
        "data": None,
        "message": "数据库繁忙，请稍后重试",
    }


async def test_unhandled_maps_pool_timeout():
    res = await unhandled_error_handler(_dummy_request(), SATimeoutError("QueuePool limit"))
    assert res.status_code == 503
    assert json.loads(res.body)["message"] == "数据库繁忙，请稍后重试"


async def test_unhandled_maps_integrity_error():
    res = await unhandled_error_handler(
        _dummy_request(),
        IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed")),
    )
    assert res.status_code == 500
    assert json.loads(res.body)["message"] == "操作冲突，请刷新后重试"


async def test_post_with_retry_raises_app_error(monkeypatch):
    class FakeClient:
        async def post(self, *_a, **_k):
            raise httpx.ConnectError("down")

    async def _no_sleep(_delay):
        return None

    monkeypatch.setattr("app.services.llm.providers.http_client", lambda: FakeClient())
    monkeypatch.setattr("app.services.llm.providers.asyncio.sleep", _no_sleep)
    with pytest.raises(AppError) as caught:
        await _post_with_retry("http://example.test/chat")
    assert caught.value.message == "模型服务暂不可用，请稍后重试"
    assert caught.value.status_code == 503
    assert caught.value.code == 503


async def test_generation_preview_llm_failure_is_app_error(client, session_factory, monkeypatch):
    data = await register(client, "previewllm@example.com")
    token = data["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="lesson.txt",
            content_type="text/plain",
            object_key="lesson.txt",
            size_bytes=20,
            status="parsed",
            extracted_text="叶绿体进行光合作用，线粒体进行呼吸作用。",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    async def boom(*_a, **_k):
        raise httpx.ConnectError("provider down")

    monkeypatch.setattr("app.services.passage_map.complete_json", boom)
    res = await client.post(
        f"/api/documents/{doc_id}/generation-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "auto", "blueprint": {}},
    )
    assert res.status_code == 503
    body = res.json()
    assert body["code"] == 503
    assert body["message"] == "模型服务暂不可用，请稍后重试"


async def test_generation_preview_parse_failure_is_app_error(client, session_factory, monkeypatch):
    data = await register(client, "previewparse@example.com")
    token = data["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="scan.pdf",
            content_type="application/pdf",
            object_key="scan.pdf",
            size_bytes=10,
            status="uploaded",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    def boom(*_a, **_k):
        raise OSError("minio down")

    monkeypatch.setattr("app.services.generation_preview.download_bytes", boom)
    res = await client.post(
        f"/api/documents/{doc_id}/generation-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={"subject": "auto", "blueprint": {}},
    )
    assert res.status_code == 503
    assert res.json()["message"] == "材料解析失败，请稍后重试"


async def test_generation_preview_db_error_is_not_parse_failure(client, session_factory, monkeypatch):
    data = await register(client, "previewdb@example.com")
    token = data["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="lesson.txt",
            content_type="text/plain",
            object_key="lesson.txt",
            size_bytes=20,
            status="parsed",
            extracted_text="叶绿体进行光合作用，线粒体进行呼吸作用。",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    async def boom(*_a, **_k):
        raise OperationalError("COMMIT", {}, Exception("database is locked"))

    monkeypatch.setattr("app.api.documents.prepare_generation_preview", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(
            f"/api/documents/{doc_id}/generation-preview",
            headers={"Authorization": f"Bearer {token}"},
            json={"subject": "auto", "blueprint": {}},
        )
    assert res.status_code == 503
    assert res.json()["message"] == "数据库繁忙，请稍后重试"


async def test_harden_llm_failure_is_app_error(client, session_factory, monkeypatch):
    registered = await register(client, "hardenfail@example.com")
    token = registered["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        quiz = QuizSet(creator_id=user_id, title="加固失败", status="ready")
        db.add(quiz)
        await db.flush()
        question = Question(
            quiz_set_id=quiz.id,
            type="single_choice",
            content="光合作用发生在哪里？",
            answer={"texts": ["叶绿体"]},
            micro_skill="detail",
        )
        db.add(question)
        await db.commit()
        question_id = question.id

    async def boom(*_a, **_k):
        raise httpx.ConnectError("critic down")

    monkeypatch.setattr("app.api.quizzes.build_choice_question", boom)
    res = await client.post(
        f"/api/quizzes/questions/{question_id}/harden",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 503
    assert res.json()["message"] == "重新生成干扰项暂不可用，请稍后重试"

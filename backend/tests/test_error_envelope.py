import json

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from starlette.requests import Request

from app.core.exceptions import unhandled_error_handler
from app.main import app
from app.models.quiz_set import QuizSet
from tests.conftest import register


async def test_unhandled_error_handler_json_body():
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/_test_unhandled",
        "raw_path": b"/api/_test_unhandled",
        "root_path": "",
        "scheme": "http",
        "query_string": b"",
        "headers": [],
        "client": ("test", 50000),
        "server": ("test", 80),
    }
    res = await unhandled_error_handler(Request(scope), RuntimeError("boom"))
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


async def test_list_quizzes_skips_failed_without_write(client: AsyncClient, session_factory):
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
    assert titles == ["好的"]
    async with session_factory() as db:
        rows = (
            await db.execute(select(QuizSet.title).where(QuizSet.creator_id == user_id))
        ).scalars().all()
    assert set(rows) == {"坏的", "好的"}

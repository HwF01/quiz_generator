import os

os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-placeholder")
os.environ.setdefault("MOCK_LLM", "true")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_quizgen.db")

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.memory_redis import MemoryRedis
from app.db.base import Base
from app.db.session import apply_sqlite_pragmas, get_db
from app.main import app
from app.models import *  # noqa: F401,F403


class FakeRedis(MemoryRedis):
    def __init__(self) -> None:
        super().__init__()
        self.down = False

    def _check(self) -> None:
        if self.down:
            raise ConnectionError("redis down")


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedis:
    redis = FakeRedis()

    def _get():
        return redis

    monkeypatch.setattr("app.core.redis.get_redis", _get)
    monkeypatch.setattr("app.services.quota.get_redis", _get)
    monkeypatch.setattr("app.services.cache.get_redis", _get)
    monkeypatch.setattr("app.services.progress.get_redis", _get)
    monkeypatch.setattr("app.main.get_redis", _get)
    return redis


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"timeout": 30},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _fk(dbapi_conn, _rec) -> None:
        apply_sqlite_pragmas(dbapi_conn)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def client(fake_redis, session_factory) -> AsyncGenerator[AsyncClient, None]:
    async def _get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def register(client: AsyncClient, email: str, password: str = "password12") -> dict:
    res = await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "nickname": "t"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["code"] == 0
    return body["data"]

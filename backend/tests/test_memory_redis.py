from pathlib import Path

from app.core.config import Settings
from app.core.memory_redis import MemoryRedis
from app.services.quota import _INCR_LIMIT_LUA, _DECR_FLOOR_LUA


async def test_memory_redis_quota_scripts():
    redis = MemoryRedis()
    used = await redis.eval(_INCR_LIMIT_LUA, 1, "quota:u:1", 2, 3600)
    assert used == 1
    used = await redis.eval(_INCR_LIMIT_LUA, 1, "quota:u:1", 2, 3600)
    assert used == 2
    assert await redis.eval(_INCR_LIMIT_LUA, 1, "quota:u:1", 2, 3600) == -1
    assert await redis.get("quota:u:1") == "2"
    assert await redis.eval(_DECR_FLOOR_LUA, 1, "quota:u:1") == 1
    assert await redis.ping() is True


def test_memory_url_and_desktop_data_dir(tmp_path: Path):
    s = Settings(
        app_env="desktop",
        secret_key="change-me-in-production",
        redis_url="memory://",
        database_url="sqlite+aiosqlite:///./quizgen.db",
        quizgen_data_dir=str(tmp_path),
    )
    assert s.use_memory_redis
    assert s.is_local_stack
    assert tmp_path.resolve().as_posix() in s.database_url
    assert s.data_dir == tmp_path.resolve()


def test_development_postgres_keeps_minio_and_worker():
    s = Settings(
        app_env="development",
        secret_key="change-me-in-production",
        redis_url="redis://redis:6379/0",
        database_url="postgresql+asyncpg://quiz:quiz@postgres:5432/quizgen",
        quizgen_data_dir=".",
    )
    assert not s.is_local_stack
    assert not s.use_memory_redis
    assert s.allow_storage_failure


def test_real_redis_url_not_memory():
    s = Settings(
        app_env="local",
        secret_key="change-me-in-production",
        redis_url="redis://localhost:6379/0",
        quizgen_data_dir=".",
    )
    assert not s.use_memory_redis

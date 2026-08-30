from typing import Any

from app.core.config import settings

_redis: Any = None


def get_redis() -> Any:
    global _redis
    if _redis is None:
        if settings.use_memory_redis:
            from app.core.memory_redis import MemoryRedis

            _redis = MemoryRedis()
        else:
            from redis.asyncio import Redis

            _redis = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=5,
            )
    return _redis


def reset_redis() -> None:
    global _redis
    _redis = None

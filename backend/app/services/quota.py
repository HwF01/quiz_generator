from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.redis import get_redis

# INCR then roll back if over limit. ARGV[1]=limit, ARGV[2]=ttl seconds.
_INCR_LIMIT_LUA = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
if n > tonumber(ARGV[1]) then
  redis.call('DECR', KEYS[1])
  return -1
end
return n
"""

_DECR_FLOOR_LUA = """
local n = redis.call('DECR', KEYS[1])
if n < 0 then
  redis.call('SET', KEYS[1], 0)
  return 0
end
return n
"""


def _key(user_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"quota:{user_id}:{day}"


def _quota_unavailable() -> AppError:
    return AppError("配额服务暂不可用，请稍后重试", code=503, status_code=503)


async def assert_quota(user_id: str, quota: int | None = None) -> int:
    limit = quota or settings.daily_gen_quota
    try:
        redis = get_redis()
        used = int(await redis.get(_key(user_id)) or 0)
    except AppError:
        raise
    except Exception as exc:
        raise _quota_unavailable() from exc
    if used >= limit:
        raise AppError("今日生成次数已用完，请明天再试或联系管理员提升额度", code=429, status_code=429)
    return used


async def incr_quota(user_id: str, quota: int | None = None) -> int:
    limit = quota or settings.daily_gen_quota
    try:
        redis = get_redis()
        n = int(
            await redis.eval(_INCR_LIMIT_LUA, 1, _key(user_id), limit, 60 * 60 * 36)
        )
    except AppError:
        raise
    except Exception as exc:
        raise _quota_unavailable() from exc
    if n < 0:
        raise AppError("今日生成次数已用完，请明天再试或联系管理员提升额度", code=429, status_code=429)
    return n


async def decr_quota(user_id: str) -> int:
    try:
        redis = get_redis()
        n = int(await redis.eval(_DECR_FLOOR_LUA, 1, _key(user_id)))
        return n
    except Exception as exc:
        raise _quota_unavailable() from exc


async def remaining(user_id: str, quota: int | None = None) -> dict:
    limit = quota or settings.daily_gen_quota
    try:
        redis = get_redis()
        used = int(await redis.get(_key(user_id)) or 0)
    except Exception as exc:
        raise _quota_unavailable() from exc
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0)}

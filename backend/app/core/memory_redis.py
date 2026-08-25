from __future__ import annotations

import asyncio


class MemoryRedis:
    """In-process Redis stand-in for local/desktop. Quota resets when the process exits."""

    def __init__(self) -> None:
        self.kv: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self._lock = asyncio.Lock()

    def _check(self) -> None:
        return

    async def get(self, key: str) -> str | None:
        self._check()
        return self.kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self._check()
        self.kv[key] = value
        return True

    async def incr(self, key: str) -> int:
        self._check()
        async with self._lock:
            n = int(self.kv.get(key) or 0) + 1
            self.kv[key] = str(n)
            return n

    async def decr(self, key: str) -> int:
        self._check()
        async with self._lock:
            n = int(self.kv.get(key) or 0) - 1
            self.kv[key] = str(n)
            return n

    async def expire(self, key: str, ttl: int) -> bool:
        self._check()
        return True

    async def ping(self) -> bool:
        self._check()
        return True

    async def hset(self, key: str, mapping: dict | None = None, **kwargs: str) -> int:
        self._check()
        self.hashes.setdefault(key, {}).update(mapping or kwargs)
        return 1

    async def hgetall(self, key: str) -> dict[str, str]:
        self._check()
        return dict(self.hashes.get(key) or {})

    async def eval(self, script: str, numkeys: int, *args: object) -> int:
        self._check()
        key = str(args[0])
        async with self._lock:
            if "INCR" in script:
                limit = int(args[1])
                n = int(self.kv.get(key) or 0) + 1
                if n > limit:
                    return -1
                self.kv[key] = str(n)
                return n
            n = int(self.kv.get(key) or 0) - 1
            if n < 0:
                self.kv[key] = "0"
                return 0
            self.kv[key] = str(n)
            return n

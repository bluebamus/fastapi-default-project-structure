"""고정 창 레이트 리밋 — ``RateLimiter`` (service-hardening ADR-016·ADR-025).

키마다 창(``window`` 초) 동안의 요청 수를 센다. 창은 그 키의 첫 hit 에 시작한다.
``MULTI`` 안에서 ``SET key 0 EX window NX`` → ``INCR`` → ``TTL`` 을 한 번에 실행한다 — 첫 hit 만
만료가 붙고(이후 ``INCR`` 은 TTL 을 보존한다), 카운트와 만료가 따로 노는 틈(INCR 뒤 EXPIRE 전에
프로세스가 죽어 영원히 남는 키)이 없다. Lua·``EXPIRE NX``(Redis 7.0) 없이 ``SET ... EX NX``(2.6.12)로 끝난다 —
이 클래스만 보면 2.6.12 면 되지만 앱 전체의 최소 버전은 ``GETDEL`` 때문에 6.2 다(``app/core/redis.py`` 의
``REDIS_MIN_VERSION``).

ponytail: 고정 창은 창 경계에서 최대 2배 버스트를 허용한다(residual-risk R-004). 막아야 하면
슬라이딩 로그(ZSET)로 바꾼다.
"""

from __future__ import annotations

from typing import NamedTuple

from redis.asyncio import Redis


class RateLimitResult(NamedTuple):
    """hit 결과. ``retry_after`` 는 현재 창이 끝날 때까지 남은 초(최소 1)."""

    allowed: bool
    retry_after: int


class RateLimiter:
    """Redis 고정 창 카운터."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window: int) -> RateLimitResult:
        """시도 하나를 세고 허용 여부를 돌려준다(``limit`` 번째까지 허용)."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window, nx=True)
            pipe.incr(key)
            pipe.ttl(key)
            _, count, ttl = await pipe.execute()
        retry_after = ttl if ttl > 0 else window
        return RateLimitResult(allowed=count <= limit, retry_after=retry_after)

    async def reset(self, key: str) -> None:
        """카운터를 지운다(예: 로그인 성공)."""
        await self._redis.delete(key)

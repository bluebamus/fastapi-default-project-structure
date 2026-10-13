"""refresh 토큰 회전 기록 — ``RefreshTokenStore`` (service-hardening ADR-015·ADR-025).

키 구조:

- ``auth:rt:{jti}`` → ``{"sub", "fam"}`` (TTL = refresh 유효 시간). 아직 쓰이지 않은 refresh 토큰.
- ``auth:user:{sub}:fams`` → 그 사용자의 family 집합(사용자 단위 폐기에 쓴다).
- ``auth:fam:{fam}:revoked`` → 폐기된 family 표시(TTL = refresh 유효 시간).

회전은 ``GETDEL`` 하나로 jti 를 소비한다 — 명령 하나가 원자적이라 같은 토큰으로 동시에 회전해도
한쪽만 값을 받는다. 값을 못 받은 쪽은 **이미 쓰인 토큰**을 내민 것이므로 재사용 탐지로 다룬다.
``GETDEL`` 은 Redis 6.2 에서 생겼고, 이 명령이 앱의 Redis 최소 버전을 정한다(``app/core/redis.py`` 의
``REDIS_MIN_VERSION`` — lifespan 이 기동 시 확인한다).

폐기 표시의 TTL 이 refresh 유효 시간이면 충분한 이유: 폐기 시점 이후에 그 family 로 새 토큰이
발급되지 않으므로, 살아 있는 토큰은 모두 폐기 시점 + 유효 시간 안에 만료된다.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis


class RefreshTokenStore:
    """refresh jti 의 1회 사용과 family 폐기를 Redis 에 기록한다."""

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        """
        Args:
            redis: lifespan 이 연 클라이언트(``get_redis`` provider 로 주입)
            ttl_seconds: refresh 토큰 유효 시간(초) — 모든 키의 TTL
        """
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _token_key(jti: str) -> str:
        return f"auth:rt:{jti}"

    @staticmethod
    def _families_key(sub: str) -> str:
        return f"auth:user:{sub}:fams"

    @staticmethod
    def _revoked_key(fam: str) -> str:
        return f"auth:fam:{fam}:revoked"

    async def register(self, jti: str, sub: str, fam: str) -> None:
        """발급한 refresh 토큰을 미사용으로 기록하고 사용자의 family 집합에 더한다."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(self._token_key(jti), json.dumps({"sub": sub, "fam": fam}), ex=self._ttl)
            pipe.sadd(self._families_key(sub), fam)
            pipe.expire(self._families_key(sub), self._ttl)
            await pipe.execute()

    async def consume(self, jti: str) -> dict[str, Any] | None:
        """jti 를 소비한다(한 번만 성공). 이미 쓰였거나 모르는 jti 면 ``None``."""
        raw = await self._redis.getdel(self._token_key(jti))
        if raw is None:
            return None
        record: dict[str, Any] = json.loads(raw)
        return record

    async def revoke_family(self, fam: str) -> None:
        """family 를 폐기한다 — 그 family 의 토큰은 이후 회전할 수 없다."""
        await self._redis.set(self._revoked_key(fam), "1", ex=self._ttl)

    async def is_family_revoked(self, fam: str) -> bool:
        """family 가 폐기됐는가."""
        return bool(await self._redis.exists(self._revoked_key(fam)))

    async def revoke_user(self, sub: str) -> None:
        """사용자의 모든 family 를 폐기한다(비활성화·삭제 시)."""
        # redis-py 의 타입은 동기·비동기 클라이언트를 한 시그니처로 적어 반환형이 합집합이다.
        families = await cast("Awaitable[set[Any]]", self._redis.smembers(self._families_key(sub)))
        async with self._redis.pipeline(transaction=True) as pipe:
            for fam in families:
                name = fam.decode() if isinstance(fam, bytes) else fam
                pipe.set(self._revoked_key(name), "1", ex=self._ttl)
            pipe.delete(self._families_key(sub))
            await pipe.execute()

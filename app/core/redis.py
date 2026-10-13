"""Redis 클라이언트 주입 provider (service-hardening ADR-011).

클라이언트의 생성·검증·종료는 lifespan(``app/core/resources.py`` 의 ``_redis``)이 소유하고
``app.state.redis`` 에 둔다. 요청 경로는 그 객체를 이 provider 하나로만 받는다 — 라우트·의존성이
``app.state`` 를 직접 읽으면 테스트가 ``dependency_overrides`` 로 바꿔 끼울 지점이 사라진다.

기동 시 서버 버전 확인(``ensure_redis_version``)도 여기 둔다 — lifespan 이 연결 직후 부른다.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, cast

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exception import ServiceUnavailableException
from app.utils.logs import get_logger

logger = get_logger("redis")

# 이 앱이 요구하는 Redis 서버 최소 버전 — 코드가 실제로 보내는 명령 중 가장 높은 요구치다
# (log-redaction ADR-003). 명령 → 도입 버전:
#   GETDEL                              6.2.0   security/refresh_store.py (refresh 회전)
#   SET key v EX n NX                   2.6.12  security/rate_limit.py (첫 hit 에만 만료)
#   MULTI·INCR·TTL·EXPIRE·SADD·SMEMBERS·EXISTS·DEL·PING  2.6 이하
# ``EXPIRE ... NX``(7.0)·Lua 는 쓰지 않는다. 쓰게 되면 이 값을 올린다 —
# ``tests/core/test_redis_version.py`` 의 계약 테스트가 소스와 이 값을 맞춰 본다.
REDIS_MIN_VERSION = (6, 2, 0)


class RedisVersionError(RuntimeError):
    """Redis 서버가 ``REDIS_MIN_VERSION`` 보다 낮다 — 기동을 멈춘다."""


def _parse_version(reported: str) -> tuple[int, int, int]:
    parts = [int(part) for part in reported.split(".")[:3]]
    parts += [0] * (3 - len(parts))
    return parts[0], parts[1], parts[2]


async def ensure_redis_version(client: Redis) -> None:
    """``INFO server`` 의 ``redis_version`` 이 최소 버전 이상인지 확인한다.

    Raises:
        RedisVersionError: 보고된 버전이 ``REDIS_MIN_VERSION`` 미만일 때. Redis 는 필수 자원이라
            (service-hardening ADR-011) 쓰는 명령이 없는 서버로 뜨는 대신 기동을 멈춘다.

    ``INFO`` 를 막아 둔 관리형 Redis 나 버전을 알 수 없는 응답이면 WARNING 을 남기고 계속한다 —
    확인할 수 없다는 사실만으로 기동을 막지는 않는다.
    """
    minimum = ".".join(map(str, REDIS_MIN_VERSION))
    try:
        # redis-py 의 타입은 동기·비동기 클라이언트를 한 시그니처로 적어 반환형이 합집합이다.
        info = await cast("Awaitable[dict[str, Any]]", client.info("server"))
        reported = str(info["redis_version"])
        version = _parse_version(reported)
    except (RedisError, KeyError, ValueError) as exc:
        logger.warning(
            "[startup] Redis 서버 버전을 확인하지 못했다(%s) — 최소 %s 이상이어야 한다",
            type(exc).__name__,
            minimum,
        )
        return
    if version < REDIS_MIN_VERSION:
        raise RedisVersionError(
            f"Redis {reported} 는 지원하지 않는다 — 최소 {minimum} 이상이 필요하다"
            " (GETDEL 을 쓴다)"
        )
    logger.info("[startup] Redis 서버 버전 %s (최소 %s)", reported, minimum)


def get_redis(request: Request) -> Redis:
    """lifespan 이 연 Redis 클라이언트를 돌려준다.

    Raises:
        ServiceUnavailableException: 클라이언트가 없을 때(lifespan 밖·종료 후) — 503.
    """
    client: Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        raise ServiceUnavailableException("Redis 를 사용할 수 없습니다.")
    return client

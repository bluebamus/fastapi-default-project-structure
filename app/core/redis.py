"""Redis 클라이언트 주입 provider (service-hardening ADR-011).

클라이언트의 생성·검증·종료는 lifespan(``app/core/resources.py`` 의 ``_redis``)이 소유하고
``app.state.redis`` 에 둔다. 요청 경로는 그 객체를 이 provider 하나로만 받는다 — 라우트·의존성이
``app.state`` 를 직접 읽으면 테스트가 ``dependency_overrides`` 로 바꿔 끼울 지점이 사라진다.
"""

from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis

from app.core.exception import ServiceUnavailableException


def get_redis(request: Request) -> Redis:
    """lifespan 이 연 Redis 클라이언트를 돌려준다.

    Raises:
        ServiceUnavailableException: 클라이언트가 없을 때(lifespan 밖·종료 후) — 503.
    """
    client: Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        raise ServiceUnavailableException("Redis 를 사용할 수 없습니다.")
    return client

"""Auth 테스트 공용 fixture — 가짜 Redis.

회전 저장소·레이트 리밋은 ``get_redis`` provider 하나에서 Redis 를 받는다. 테스트는 그 provider 만
fakeredis 로 바꿔 끼워 실물 클래스(``RefreshTokenStore``·``RateLimiter``)를 그대로 시험한다
(service-hardening C-1 — 가짜 Protocol 을 만들지 않는다). 테스트마다 새 서버라 카운터가 섞이지 않는다.
"""

import pytest_asyncio
from fakeredis import FakeAsyncRedis


@pytest_asyncio.fixture
async def fake_redis():
    client = FakeAsyncRedis()
    yield client
    await client.aclose()

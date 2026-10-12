"""``RateLimiter`` — Redis 고정 창 (service-hardening ADR-016)."""

from __future__ import annotations

import asyncio

import pytest_asyncio
from fakeredis import FakeAsyncRedis

from app.core.security.rate_limit import RateLimiter


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def limiter(redis):
    return RateLimiter(redis)


async def test_allows_up_to_the_limit_then_denies(limiter):
    results = [await limiter.hit("k", limit=3, window=60) for _ in range(4)]

    assert [r.allowed for r in results] == [True, True, True, False]


async def test_denial_reports_seconds_until_the_window_ends(limiter):
    for _ in range(2):
        result = await limiter.hit("k", limit=1, window=60)

    assert result.allowed is False
    assert 0 < result.retry_after <= 60


async def test_window_starts_at_the_first_hit_and_is_not_extended(limiter, redis):
    """이후 hit 이 만료를 다시 걸면 끊임없이 두드리는 클라이언트는 영원히 풀리지 않는다."""
    await limiter.hit("k", limit=10, window=60)
    await redis.expire("k", 5)  # 창의 끝이 가까워진 상황

    result = await limiter.hit("k", limit=10, window=60)

    assert result.retry_after <= 5
    assert await redis.ttl("k") <= 5


async def test_counter_restarts_after_the_window_expires(limiter):
    await limiter.hit("k", limit=1, window=1)
    assert (await limiter.hit("k", limit=1, window=1)).allowed is False

    await asyncio.sleep(1.1)

    assert (await limiter.hit("k", limit=1, window=1)).allowed is True


async def test_reset_clears_the_counter(limiter):
    for _ in range(2):
        await limiter.hit("k", limit=1, window=60)

    await limiter.reset("k")

    assert (await limiter.hit("k", limit=1, window=60)).allowed is True


async def test_keys_are_counted_independently(limiter):
    await limiter.hit("a", limit=1, window=60)

    assert (await limiter.hit("b", limit=1, window=60)).allowed is True

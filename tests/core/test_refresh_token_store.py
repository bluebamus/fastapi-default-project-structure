"""``RefreshTokenStore`` — 1회 소비·family 폐기·사용자 폐기 (service-hardening ADR-015, INV-6).

실물 클래스를 fakeredis 로 시험한다(가짜 Protocol 없음, C-1).
"""

from __future__ import annotations

import asyncio

import pytest_asyncio
from fakeredis import FakeAsyncRedis

from app.core.security.refresh_store import RefreshTokenStore

TTL = 3600


@pytest_asyncio.fixture
async def redis():
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def store(redis):
    return RefreshTokenStore(redis, TTL)


async def test_registered_token_can_be_consumed_once(store):
    await store.register("jti-1", "user-1", "fam-1")

    assert await store.consume("jti-1") == {"sub": "user-1", "fam": "fam-1"}
    assert await store.consume("jti-1") is None


async def test_unknown_token_is_not_consumable(store):
    assert await store.consume("never-issued") is None


async def test_concurrent_consumption_lets_exactly_one_win(store):
    await store.register("jti-1", "user-1", "fam-1")

    results = await asyncio.gather(*(store.consume("jti-1") for _ in range(5)))

    assert sum(result is not None for result in results) == 1


async def test_keys_expire_with_the_refresh_lifetime(store, redis):
    await store.register("jti-1", "user-1", "fam-1")

    assert 0 < await redis.ttl("auth:rt:jti-1") <= TTL
    assert 0 < await redis.ttl("auth:user:user-1:fams") <= TTL
    assert await redis.smembers("auth:user:user-1:fams") == {b"fam-1"}


async def test_revoked_family_is_reported_and_expires(store, redis):
    assert await store.is_family_revoked("fam-1") is False

    await store.revoke_family("fam-1")

    assert await store.is_family_revoked("fam-1") is True
    assert 0 < await redis.ttl("auth:fam:fam-1:revoked") <= TTL


async def test_revoke_user_revokes_every_family_of_that_user_only(store, redis):
    await store.register("a1", "user-1", "fam-a")
    await store.register("b1", "user-1", "fam-b")
    await store.register("c1", "user-2", "fam-c")

    await store.revoke_user("user-1")

    assert await store.is_family_revoked("fam-a") is True
    assert await store.is_family_revoked("fam-b") is True
    assert await store.is_family_revoked("fam-c") is False
    assert await redis.exists("auth:user:user-1:fams") == 0

"""liveness(/health)와 readiness(/ready) 분리 계약 — NFR-006.

둘을 한 엔드포인트로 합치면 오케스트레이터가 잘못된 판단을 한다.
DB 가 잠깐 흔들릴 때 /health 까지 실패하면 **살아 있는 프로세스가 재시작**되고,
반대로 /ready 가 DB 를 보지 않으면 준비되지 않은 인스턴스로 트래픽이 들어온다.

    /health : 프로세스 생존만. 외부 연결을 검사하지 않는다.
    /ready  : writer DB 에 SELECT 1 + Redis PING (각 2초 timeout, 동시에). 둘 다 성공 200,
              하나라도 실패·timeout 503 (service-hardening ADR-011).

503 응답에 DSN 이나 내부 DB 오류 문구가 실려서는 안 된다 — 헬스 엔드포인트는 보통
인증 없이 열려 있다. 로그에도 대상과 예외 타입만 남긴다.

Redis 는 lifespan 이 연 실물 대신 ``get_redis`` provider 를 가짜 클라이언트로 바꿔 끼운다.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient

import main
from app.core.db import session as db_session_module
from app.core.redis import get_redis


class FakeRedis:
    """``ping`` 만 가진 가짜 — ``/ready`` 가 쓰는 유일한 명령이다."""

    def __init__(self) -> None:
        self.error: BaseException | None = None
        self.hang = False
        self.pings = 0

    async def ping(self) -> bool:
        self.pings += 1
        if self.hang:
            await asyncio.sleep(3600)
        if self.error is not None:
            raise self.error
        return True


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
async def client(redis):
    main.app.dependency_overrides[get_redis] = lambda: redis
    transport = ASGITransport(app=main.app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        main.app.dependency_overrides.pop(get_redis, None)


async def _db_ok(timeout: float | None = None) -> None:
    return None


async def test_health_does_not_touch_the_database(client, monkeypatch):
    """/health 는 DB 를 건드리지 않는다 — 프로세스 생존만 본다."""
    called: list[str] = []

    async def fail_if_called(*args, **kwargs) -> None:
        called.append("ping")
        raise AssertionError("liveness 가 DB 를 검사했다")

    monkeypatch.setattr(main, "ping_writer_db", fail_if_called, raising=False)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert called == []


async def test_ready_returns_200_when_database_and_redis_answer(client, redis, monkeypatch):
    monkeypatch.setattr(main, "ping_writer_db", _db_ok)

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert redis.pings == 1, "/ready 가 Redis 를 확인하지 않았다"


async def test_ready_returns_503_when_redis_ping_fails(client, redis, monkeypatch):
    monkeypatch.setattr(main, "ping_writer_db", _db_ok)
    redis.error = ConnectionError(
        "Error 111 connecting to redis-internal:6379. Connection refused."
    )

    response = await client.get("/ready")

    assert response.status_code == 503
    assert "redis-internal" not in response.text
    assert "refused" not in response.text


async def test_ready_returns_503_when_redis_ping_times_out(client, redis, monkeypatch):
    """응답 없는 Redis 가 /ready 를 붙잡지 못한다 — 예산 안에서 503."""
    monkeypatch.setattr(main, "ping_writer_db", _db_ok)
    monkeypatch.setattr(main, "READINESS_TIMEOUT_SECONDS", 0.05)
    redis.hang = True

    response = await asyncio.wait_for(client.get("/ready"), timeout=5)

    assert response.status_code == 503


async def test_ready_checks_database_and_redis_concurrently(client, monkeypatch):
    """둘을 순서대로 기다리면 최악 지연이 예산의 두 배가 된다 — 동시에 시작해야 한다."""
    redis_started = asyncio.Event()

    async def db_waits_for_redis(timeout: float | None = None) -> None:
        # Redis ping 이 DB 확인이 끝나기 전에 시작돼야 이 대기가 풀린다.
        await asyncio.wait_for(redis_started.wait(), timeout=1)

    class _SignallingRedis(FakeRedis):
        async def ping(self) -> bool:
            redis_started.set()
            return True

    main.app.dependency_overrides[get_redis] = _SignallingRedis
    monkeypatch.setattr(main, "ping_writer_db", db_waits_for_redis)

    response = await client.get("/ready")

    assert response.status_code == 200


async def test_ready_returns_503_when_redis_client_is_missing(monkeypatch):
    """lifespan 밖(클라이언트 없음)이면 provider 가 503 으로 막는다."""
    monkeypatch.setattr(main, "ping_writer_db", _db_ok)
    monkeypatch.setattr(main.app.state, "redis", None, raising=False)
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        response = await c.get("/ready")

    assert response.status_code == 503


async def test_ready_logs_only_target_and_exception_type(client, redis, monkeypatch, caplog):
    """실패 로그에도 원문(호스트·자격증명)이 없다 — 대상과 예외 타입만."""

    async def db_boom(timeout: float | None = None) -> None:
        raise RuntimeError("(1045, 'Access denied') for mysql://app:s3cr3t@db-internal/shop")

    monkeypatch.setattr(main, "ping_writer_db", db_boom)
    redis.error = ConnectionError("cannot reach redis://:s3cr3t@redis-internal:6379/0")

    with caplog.at_level(logging.WARNING, logger=main.logger.name):
        response = await client.get("/ready")

    assert response.status_code == 503
    records = [
        r for r in caplog.records if r.name == main.logger.name and hasattr(r, "readiness_target")
    ]
    messages = [r.getMessage() for r in records]
    assert messages == [
        "[Readiness] DB 준비 확인 실패: RuntimeError",
        "[Readiness] Redis 준비 확인 실패: ConnectionError",
    ]
    assert all("s3cr3t" not in m and "internal" not in m for m in messages)
    assert [r.readiness_target for r in records] == ["DB", "Redis"]


async def test_ready_returns_503_on_database_error(client, monkeypatch):
    async def boom(timeout: float | None = None) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main, "ping_writer_db", boom)

    response = await client.get("/ready")

    assert response.status_code == 503


async def test_ready_returns_503_on_timeout(client, monkeypatch):
    async def hang(timeout: float | None = None) -> None:
        raise TimeoutError

    monkeypatch.setattr(main, "ping_writer_db", hang)

    response = await client.get("/ready")

    assert response.status_code == 503


async def test_ready_503_hides_internal_details(client, monkeypatch):
    """DSN·드라이버 오류 원문이 응답에 새어나가면 안 된다."""
    secret = "mysql+aiomysql://app:s3cr3t@db-internal:3306/shop"

    async def boom(timeout: float | None = None) -> None:
        raise RuntimeError(f"(1045, 'Access denied') for {secret}")

    monkeypatch.setattr(main, "ping_writer_db", boom)

    response = await client.get("/ready")
    body = response.text

    assert response.status_code == 503
    assert "s3cr3t" not in body
    assert "db-internal" not in body
    assert "1045" not in body
    assert "Access denied" not in body


def test_readiness_timeout_is_two_seconds():
    """확정 정책 5 — writer DB SELECT 1, 2초 timeout."""
    assert db_session_module.READINESS_TIMEOUT_SECONDS == 2.0


async def test_ping_writer_db_times_out(monkeypatch):
    """ping 자체가 timeout 예산을 지킨다 — 응답 없는 DB 가 요청을 붙잡지 못한다."""

    class _HangingConnection:
        async def __aenter__(self):
            await asyncio.sleep(3600)

        async def __aexit__(self, *exc_info):
            return False

    class _HangingEngine:
        def connect(self):
            return _HangingConnection()

    # AsyncEngine 은 슬롯이라 속성 교체가 안 된다 — 모듈 전역 engine 을 갈아끼운다.
    monkeypatch.setattr(db_session_module, "engine", _HangingEngine())

    with pytest.raises(TimeoutError):
        await db_session_module.ping_writer_db(timeout=0.05)

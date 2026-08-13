"""liveness(/health)와 readiness(/ready) 분리 계약 — NFR-006.

둘을 한 엔드포인트로 합치면 오케스트레이터가 잘못된 판단을 한다.
DB 가 잠깐 흔들릴 때 /health 까지 실패하면 **살아 있는 프로세스가 재시작**되고,
반대로 /ready 가 DB 를 보지 않으면 준비되지 않은 인스턴스로 트래픽이 들어온다.

    /health : 프로세스 생존만. 외부 연결을 검사하지 않는다.
    /ready  : writer DB 에 SELECT 1 (2초 timeout). 성공 200, 실패·timeout 503.

503 응답에 DSN 이나 내부 DB 오류 문구가 실려서는 안 된다 — 헬스 엔드포인트는 보통
인증 없이 열려 있다.
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

import main
from app.core.db import session as db_session_module


@pytest.fixture
async def client():
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


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


async def test_ready_returns_200_when_database_answers(client, monkeypatch):
    async def ok(timeout: float | None = None) -> None:
        return None

    monkeypatch.setattr(main, "ping_writer_db", ok)

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


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

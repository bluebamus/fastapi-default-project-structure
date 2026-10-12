"""트랜잭션 경계 회귀 테스트 (검수 W2/REQ-009).

읽기 전용 인증 경로(`get_current_user` → `/me`)는 세션을 커밋해서는 안 된다.
커밋하는 `get_auth_service` 에 의존하면, 인증+쓰기 의존성을 함께 쓰는
엔드포인트에서 한 세션에 커밋 주체가 둘이 되어 부분 저장(이중 커밋) 위험이
생긴다. 또한 인증된 읽기 요청마다 불필요한 COMMIT 왕복이 발생한다.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.redis import get_redis
from app.features.user.models.models import User  # noqa: F401  (register table)
from main import app
from tests.session_overrides import override_db_sessions


@pytest_asyncio.fixture
async def counting_client(fake_redis):
    """세션 commit 횟수를 세는 클라이언트. `counter["on"]` 구간의 커밋만 집계."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    counter = {"on": False, "count": 0}

    def _wrap_session(session):
        original_commit = session.commit

        async def _counting_commit(*args, **kwargs):
            if counter["on"]:
                counter["count"] += 1
            return await original_commit(*args, **kwargs)

        session.commit = _counting_commit  # type: ignore[method-assign]

    override_db_sessions(app, maker, _wrap_session)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, counter
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_me_read_only_path_does_not_commit(counting_client):
    client, counter = counting_client

    # 준비: 쓰기 경로(register/login)는 정당하게 커밋 — 집계 대상 아님
    await client.post(
        "/api/v1/auth/register",
        json={"username": "eve", "email": "eve@ex.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": "eve", "password": "password123"}
    )
    token = login.json()["access_token"]

    # 측정: 읽기 전용 /me 동안의 커밋만 집계 → 0 이어야 한다
    counter["on"] = True
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    counter["on"] = False

    assert me.status_code == 200
    assert counter["count"] == 0, f"읽기 전용 인증이 {counter['count']}회 커밋함"


async def test_login_without_rehash_does_not_commit(counting_client):
    """Argon2 로 저장된 사용자의 로그인은 DB 를 바꾸지 않는다 — 커밋도 없다(재해시일 때만 1회)."""
    client, counter = counting_client
    await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@ex.com", "password": "password123"},
    )

    counter["on"] = True
    login = await client.post(
        "/api/v1/auth/login", data={"username": "bob", "password": "password123"}
    )
    counter["on"] = False

    assert login.status_code == 200
    assert counter["count"] == 0

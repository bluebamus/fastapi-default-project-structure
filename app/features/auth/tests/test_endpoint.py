"""Auth 엔드포인트 테스트 — register/login/me/refresh/logout 전체 경로.

DB 는 in-memory sqlite(공용 세션 헬퍼), Redis 는 ``get_redis`` override 로 fakeredis 를 넣는다.
"""

import bcrypt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.redis import get_redis
from app.features.user.models.models import User
from config import jwt_settings, middleware_settings
from main import app
from tests.session_overrides import override_db_sessions


@pytest_asyncio.fixture
async def env(fake_redis):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    override_db_sessions(app, maker)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, maker
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def client(env):
    return env[0]


async def _register(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@ex.com", "password": password},
    )


async def _login(client, username="alice", password="password123", headers=None):
    return await client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
        headers=headers,
    )


async def _refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _me(client, access):
    return await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})


# =============================================================================
# 회원가입
# =============================================================================
async def test_register_returns_user_without_password(client):
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "password" not in body and "hashed_password" not in body
    assert body["is_active"] is True


async def test_register_stores_argon2_hash(env):
    client, maker = env
    await _register(client)
    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password))
    assert stored.startswith("$argon2id$")


async def test_register_duplicate_username_409(client):
    await _register(client)
    resp = await _register(client)
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "AUTH_USERNAME_DUPLICATE"


async def test_register_rejects_short_password(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@ex.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_register_is_rate_limited_per_ip(client):
    limit = jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS
    for i in range(limit):
        assert (await _register(client, username=f"user{i}")).status_code == 201

    resp = await _register(client, username="one-too-many")

    assert resp.status_code == 429
    assert resp.json()["error_code"] == "TOO_MANY_REQUESTS"
    retry_after = int(resp.headers["Retry-After"])
    assert 0 < retry_after <= jwt_settings.AUTH_REGISTER_WINDOW_SECONDS


# =============================================================================
# 로그인 · me
# =============================================================================
async def test_login_and_access_me(client):
    await _register(client)
    login = await _login(client)
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == jwt_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    me = await _me(client, tokens["access_token"])
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_wrong_password_401(client):
    await _register(client)
    resp = await _login(client, password="wrong-password")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


async def test_me_without_token_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_401(client):
    resp = await _me(client, "not-a-real-token")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_me_rejects_refresh_token_401(client):
    await _register(client)
    tokens = (await _login(client)).json()
    assert (await _me(client, tokens["refresh_token"])).status_code == 401


async def test_login_with_legacy_bcrypt_hash_persists_argon2_rehash(env):
    """이전 버전이 저장한 bcrypt 해시(72바이트 절단)로 로그인되고, 새 Argon2 해시가 저장된다."""
    client, maker = env
    password = "레거시-" + "p" * 90  # UTF-8 72바이트를 넘는다 — 절단 규칙까지 맞아야 한다
    legacy = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)).decode()
    async with maker() as session:
        session.add(User(username="old", email="old@ex.com", hashed_password=legacy))
        await session.commit()

    assert (await _login(client, username="old", password=password)).status_code == 200

    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password).where(User.username == "old"))
    assert stored.startswith("$argon2id$")
    # 이전된 해시로 다시 로그인된다.
    assert (await _login(client, username="old", password=password)).status_code == 200


async def test_login_is_rate_limited_per_ip_and_username(client):
    await _register(client)
    limit = jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS
    for _ in range(limit):
        assert (await _login(client, password="wrong-password")).status_code == 401

    # 맞는 비밀번호여도 한도를 넘기면 429 — 자격 검증 전에 막는다.
    resp = await _login(client)

    assert resp.status_code == 429
    retry_after = int(resp.headers["Retry-After"])
    assert 0 < retry_after <= jwt_settings.AUTH_LOGIN_WINDOW_SECONDS


async def test_login_rate_limit_ignores_username_case(client):
    await _register(client)
    for i in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS):
        name = "ALICE" if i % 2 else "alice"
        await _login(client, username=name, password="wrong-password")

    assert (await _login(client, username="Alice")).status_code == 429


async def test_login_rate_limit_is_not_bypassed_by_forwarded_for(client, monkeypatch):
    """신뢰 프록시 홉이 0 이면 X-Forwarded-For 를 바꿔도 같은 IP 로 센다(ADR-006)."""
    # 전제(홉 0)를 못 박는다 — 로컬 .env 가 홉을 1 이상으로 두면 XFF 가 신뢰돼 결과가 바뀐다.
    monkeypatch.setattr(middleware_settings, "TRUSTED_PROXY_HOPS", 0)
    await _register(client)
    for i in range(jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS):
        headers = {"X-Forwarded-For": f"198.51.100.{i}"}
        await _login(client, password="wrong-password", headers=headers)

    resp = await _login(client, headers={"X-Forwarded-For": "198.51.100.200"})

    assert resp.status_code == 429


async def test_successful_login_resets_ip_username_counter(client):
    await _register(client)
    limit = jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS
    for _ in range(limit - 1):
        await _login(client, password="wrong-password")
    assert (await _login(client)).status_code == 200

    # 성공이 카운터를 지웠으므로 다음 실패는 429 가 아니라 401 이다.
    assert (await _login(client, password="wrong-password")).status_code == 401


async def test_login_is_rate_limited_per_ip_across_usernames(client, monkeypatch):
    monkeypatch.setattr(jwt_settings, "AUTH_LOGIN_IP_MAX_ATTEMPTS", 3)
    for i in range(3):
        assert (await _login(client, username=f"nobody{i}")).status_code == 401

    resp = await _login(client, username="someone-else")

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


# =============================================================================
# 회전 · 재사용 탐지 · 로그아웃
# =============================================================================
async def test_refresh_rotates_and_issues_working_access_token(client):
    await _register(client)
    first = (await _login(client)).json()

    resp = await _refresh(client, first["refresh_token"])

    assert resp.status_code == 200
    rotated = resp.json()
    assert rotated["refresh_token"] != first["refresh_token"]
    assert (await _me(client, rotated["access_token"])).status_code == 200


async def test_refresh_reuse_revokes_the_whole_family(client):
    """이미 쓴 refresh 를 다시 내면 401 이고, 그 사이 발급된 새 refresh 도 함께 막힌다."""
    await _register(client)
    first = (await _login(client)).json()
    second = (await _refresh(client, first["refresh_token"])).json()

    reuse = await _refresh(client, first["refresh_token"])
    assert reuse.status_code == 401
    assert reuse.json()["error_code"] == "AUTH_INVALID_TOKEN"

    assert (await _refresh(client, second["refresh_token"])).status_code == 401


async def test_reuse_does_not_touch_other_families(client):
    """재사용 탐지는 그 family 만 폐기한다 — 다른 기기의 로그인은 살아 있다."""
    await _register(client)
    device_a = (await _login(client)).json()
    device_b = (await _login(client)).json()
    await _refresh(client, device_a["refresh_token"])
    await _refresh(client, device_a["refresh_token"])  # 재사용 → A family 폐기

    assert (await _refresh(client, device_b["refresh_token"])).status_code == 200


async def test_refresh_rejects_access_token_401(client):
    await _register(client)
    login = await _login(client)
    resp = await _refresh(client, login.json()["access_token"])
    assert resp.status_code == 401


async def test_refresh_for_deactivated_user_401(env):
    client, maker = env
    await _register(client)
    tokens = (await _login(client)).json()
    async with maker() as session:
        user = await session.scalar(select(User))
        user.is_active = False
        await session.commit()

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_logout_revokes_refresh_and_is_idempotent(client):
    await _register(client)
    tokens = (await _login(client)).json()

    first = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    again = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert first.status_code == 204 and first.content == b""
    assert again.status_code == 204
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


async def test_logout_with_invalid_token_401(client):
    resp = await client.post("/api/v1/auth/logout", json={"refresh_token": "garbage"})
    assert resp.status_code == 401


# =============================================================================
# 인증 사용자 조회는 primary (integration-e2e ADR-014)
# =============================================================================
async def test_current_user_is_read_from_primary_not_a_lagging_replica():
    """replica 에 아직 없는(복제 지연) 사용자의 유효한 토큰이 401 이 되지 않는다.

    writer·reader 를 서로 다른 sqlite 로 두고 사용자는 writer 에만 넣는다 — reader 에서 읽으면 401 이다.
    세션은 앱과 같은 읽기 전용 표시를 달아, 조회가 primary 로 가도 쓰기 차단은 그대로인지 함께 본다.
    """
    from app.core.db.router import DatabaseRouter, create_routing_sessionmaker, mark_read_only
    from app.core.security.authorization import Principal
    from app.features.auth.dependencies.auth_dependencies import get_current_user

    engines = []
    for _ in range(2):
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        engines.append(engine)
    writer, reader = engines
    async with async_sessionmaker(writer)() as session:
        session.add(
            User(id="u-1", username="lagged", email="lagged@example.com", hashed_password="x")
        )
        await session.commit()
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        mark_read_only(session)
        user = await get_current_user(Principal("u-1", "lagged", False), session)

    assert user.username == "lagged"
    for engine in engines:
        await engine.dispose()

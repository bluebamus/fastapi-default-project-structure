"""Auth 엔드포인트 테스트 — register/login/me/refresh 전체 경로 (in-memory sqlite)."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_session
from app.domains.user.models.models import User  # noqa: F401  (register table)
from main import app


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


async def _register(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@ex.com", "password": password},
    )


async def _login(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )


async def test_register_returns_user_without_password(client):
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "password" not in body and "hashed_password" not in body
    assert body["is_active"] is True


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


async def test_login_and_access_me(client):
    await _register(client)
    login = await _login(client)
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
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
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_refresh_issues_working_access_token(client):
    await _register(client)
    login = await _login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]}
    )
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 200


async def test_refresh_rejects_access_token_401(client):
    await _register(client)
    login = await _login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login.json()["access_token"]}
    )
    assert resp.status_code == 401

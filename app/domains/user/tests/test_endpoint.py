"""User CRUD 엔드포인트 테스트.

AppRegistry 자동 등록 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_session 오버라이드)로 검증한다.
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.bootstrap import create_app
from app.core.db.session import Base, get_session
from app.domains.user.models.models import User  # noqa: F401  (register table)


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

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await engine.dispose()


def test_user_auto_registered():
    """config.py 만으로 user CRUD 라우터가 자동 발견·마운트된다."""
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/user/users" in paths
    assert "/api/v1/user/users/{user_id}" in paths


async def test_create_and_get_user(client):
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "alice", "email": "alice@example.com"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert body["is_active"] is True
    user_id = body["id"]

    got = await client.get(f"/api/v1/user/users/{user_id}")
    assert got.status_code == 200
    assert got.json()["email"] == "alice@example.com"


async def test_list_users(client):
    await client.post("/api/v1/user/users", json={"username": "a", "email": "a@x.com"})
    await client.post("/api/v1/user/users", json={"username": "b", "email": "b@x.com"})

    resp = await client.get("/api/v1/user/users")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_user_deactivate(client):
    created = await client.post(
        "/api/v1/user/users", json={"username": "bob", "email": "bob@x.com"}
    )
    user_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/user/users/{user_id}", json={"is_active": False}
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_delete_user(client):
    created = await client.post(
        "/api/v1/user/users", json={"username": "carol", "email": "carol@x.com"}
    )
    user_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/user/users/{user_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/user/users/{user_id}")
    assert got.status_code == 404


async def test_duplicate_username_returns_409(client):
    await client.post(
        "/api/v1/user/users", json={"username": "dup", "email": "d1@x.com"}
    )
    resp = await client.post(
        "/api/v1/user/users", json={"username": "dup", "email": "d2@x.com"}
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "USER_USERNAME_DUPLICATE"


async def test_get_missing_user_returns_404(client):
    resp = await client.get("/api/v1/user/users/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "USER_NOT_FOUND"


async def test_create_rejects_invalid_email(client):
    resp = await client.post(
        "/api/v1/user/users", json={"username": "x", "email": "not-an-email"}
    )
    assert resp.status_code == 422

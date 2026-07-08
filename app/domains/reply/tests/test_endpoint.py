"""Reply CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_session 오버라이드)로 검증한다.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_session
from app.domains.reply.models.models import Reply  # noqa: F401  (register table)
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


def test_reply_auto_registered():
    """디렉터리 컨벤션만으로 reply CRUD 라우터가 자동 발견·마운트된다."""
    paths = {r.path for r in app.routes}
    assert "/api/v1/reply/replies" in paths
    assert "/api/v1/reply/replies/{reply_id}" in paths


async def test_create_and_get_reply(client):
    resp = await client.post(
        "/api/v1/reply/replies",
        json={"content": "좋은 글이네요", "author": "lee", "post_id": "p1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "좋은 글이네요"
    assert body["id"]
    reply_id = body["id"]

    got = await client.get(f"/api/v1/reply/replies/{reply_id}")
    assert got.status_code == 200
    assert got.json()["post_id"] == "p1"


async def test_list_replies(client):
    await client.post("/api/v1/reply/replies", json={"content": "a"})
    await client.post("/api/v1/reply/replies", json={"content": "b"})

    resp = await client.get("/api/v1/reply/replies")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_reply(client):
    created = await client.post("/api/v1/reply/replies", json={"content": "old"})
    reply_id = created.json()["id"]

    resp = await client.patch(f"/api/v1/reply/replies/{reply_id}", json={"content": "new"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


async def test_delete_reply(client):
    created = await client.post("/api/v1/reply/replies", json={"content": "c"})
    reply_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/reply/replies/{reply_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/reply/replies/{reply_id}")
    assert got.status_code == 404


async def test_get_missing_reply_returns_404(client):
    resp = await client.get("/api/v1/reply/replies/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "REPLY_NOT_FOUND"


async def test_create_rejects_empty_content(client):
    resp = await client.post("/api/v1/reply/replies", json={"content": ""})
    assert resp.status_code == 422

"""SNS CRUD 엔드포인트 테스트.

AppRegistry 자동 등록 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_session 오버라이드)로 검증한다.
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.bootstrap import create_app
from app.core.db.session import Base, get_session
from app.domains.sns.models.models import SnsPost  # noqa: F401  (register table)


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


def test_sns_auto_registered():
    """디렉터리 컨벤션만으로 sns CRUD 라우터가 자동 발견·마운트된다."""
    app = create_app()
    paths = {r.path for r in app.routes}
    assert "/api/v1/sns/posts" in paths
    assert "/api/v1/sns/posts/{post_id}" in paths


async def test_create_and_get_post(client):
    resp = await client.post(
        "/api/v1/sns/posts",
        json={"content": "오늘 날씨 좋다", "author": "park"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "오늘 날씨 좋다"
    assert body["like_count"] == 0
    post_id = body["id"]

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 200
    assert got.json()["author"] == "park"


async def test_list_posts(client):
    await client.post("/api/v1/sns/posts", json={"content": "a"})
    await client.post("/api/v1/sns/posts", json={"content": "b"})

    resp = await client.get("/api/v1/sns/posts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "old"})
    post_id = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/sns/posts/{post_id}", json={"content": "new"}
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


async def test_delete_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "c"})
    post_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/sns/posts/{post_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 404


async def test_get_missing_post_returns_404(client):
    resp = await client.get("/api/v1/sns/posts/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "SNS_POST_NOT_FOUND"


async def test_create_rejects_empty_content(client):
    resp = await client.post("/api/v1/sns/posts", json={"content": ""})
    assert resp.status_code == 422

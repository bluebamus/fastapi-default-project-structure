"""Catalog(ORM 예제) API 통합 테스트 — SCN-ORM-001, TEST-002/003.

in-memory sqlite 로 View → Dependency → Service → Repository → ORM 전 구간을 돈다.
commit 횟수까지 세는 이유는 트랜잭션 경계가 이 프로젝트의 핵심 계약이기 때문이다
(조회 0회 / 쓰기 정확히 1회).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.catalog.models.models import Product  # noqa: F401  (테이블 등록)
from main import app

BASE = "/api/v1/catalog/products"


@pytest_asyncio.fixture
async def client():
    """앱 전체를 sqlite 로 돌리고 commit 횟수를 세는 클라이언트."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    counter = {"commits": 0}

    async def _override_session():
        async with maker() as db_session:
            original_commit = db_session.commit

            async def _counting_commit(*args, **kwargs):
                counter["commits"] += 1
                return await original_commit(*args, **kwargs)

            db_session.commit = _counting_commit  # type: ignore[method-assign]
            yield db_session

    # 조회는 read-only, 쓰기는 writer 세션을 쓴다 — 둘 다 같은 sqlite 로 보낸다.
    app.dependency_overrides[get_writer_db_session] = _override_session
    app.dependency_overrides[get_read_only_db_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client, counter
    app.dependency_overrides.clear()
    await engine.dispose()


async def _create(http_client, **overrides) -> dict:
    payload = {"name": "기계식 키보드", "price": "129.00"} | overrides
    response = await http_client.post(BASE, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# =============================================================================
# 성공 경로
# =============================================================================
async def test_create_returns_201_with_generated_id(client):
    http_client, _ = client
    created = await _create(http_client)

    assert created["id"], "모델 default 로 UUID 가 채워져야 한다"
    assert created["name"] == "기계식 키보드"
    assert Decimal(created["price"]) == Decimal("129.00")
    assert created["is_active"] is True
    assert "created_at" in created and "updated_at" in created


async def test_get_returns_the_created_product(client):
    http_client, _ = client
    created = await _create(http_client)

    response = await http_client.get(f"{BASE}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_list_paginates_and_reports_total(client):
    http_client, _ = client
    for index in range(3):
        await _create(http_client, name=f"상품-{index}")

    response = await http_client.get(BASE, params={"skip": 0, "limit": 2})

    body = response.json()
    assert response.status_code == 200
    assert len(body["items"]) == 2
    assert body["total"] == 3
    assert body["skip"] == 0 and body["limit"] == 2


async def test_list_active_only_filters_inactive(client):
    http_client, _ = client
    await _create(http_client, name="판매중", is_active=True)
    await _create(http_client, name="단종", is_active=False)

    response = await http_client.get(BASE, params={"active_only": True})

    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["판매중"]


async def test_patch_updates_only_given_fields(client):
    http_client, _ = client
    created = await _create(http_client)

    response = await http_client.patch(f"{BASE}/{created['id']}", json={"price": "99.50"})

    body = response.json()
    assert response.status_code == 200
    assert Decimal(body["price"]) == Decimal("99.50")
    assert body["name"] == created["name"], "전달하지 않은 필드는 유지돼야 한다"


async def test_delete_returns_204_and_then_404(client):
    http_client, _ = client
    created = await _create(http_client)

    assert (await http_client.delete(f"{BASE}/{created['id']}")).status_code == 204
    assert (await http_client.get(f"{BASE}/{created['id']}")).status_code == 404


# =============================================================================
# 오류 경로
# =============================================================================
async def test_missing_product_returns_404(client):
    http_client, _ = client
    response = await http_client.get(f"{BASE}/존재하지-않는-id")

    assert response.status_code == 404
    assert response.json()["error_code"] == "CATALOG_PRODUCT_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "price": "10.00"},
        {"name": "정상", "price": "0"},
        {"name": "정상", "price": "-1.00"},
        {"price": "10.00"},
    ],
)
async def test_invalid_payload_returns_422(client, payload):
    http_client, _ = client
    response = await http_client.post(BASE, json=payload)
    assert response.status_code == 422


async def test_limit_upper_bound_is_enforced(client):
    """무제한 조회를 허용하지 않는다 (NFR-002)."""
    http_client, _ = client
    response = await http_client.get(BASE, params={"limit": 1000})
    assert response.status_code == 422


# =============================================================================
# 트랜잭션 경계 (TEST-002)
# =============================================================================
async def test_read_path_does_not_commit(client):
    http_client, counter = client
    await _create(http_client)
    counter["commits"] = 0

    await http_client.get(BASE)
    await http_client.get(f"{BASE}/없는-id")

    assert counter["commits"] == 0, "조회 경로가 커밋했다 (TX-002 위반)"


async def test_write_path_commits_exactly_once(client):
    http_client, counter = client

    counter["commits"] = 0
    created = await _create(http_client)
    assert counter["commits"] == 1, "생성이 정확히 1회 커밋해야 한다"

    counter["commits"] = 0
    await http_client.patch(f"{BASE}/{created['id']}", json={"price": "1.00"})
    assert counter["commits"] == 1, "수정이 정확히 1회 커밋해야 한다"

    counter["commits"] = 0
    await http_client.delete(f"{BASE}/{created['id']}")
    assert counter["commits"] == 1, "삭제가 정확히 1회 커밋해야 한다"


async def test_failed_write_does_not_commit(client):
    """없는 상품 삭제는 404 이고 커밋이 0회여야 한다."""
    http_client, counter = client
    counter["commits"] = 0

    response = await http_client.delete(f"{BASE}/없는-id")

    assert response.status_code == 404
    assert counter["commits"] == 0, "실패 경로가 커밋했다 (TX-004 위반)"

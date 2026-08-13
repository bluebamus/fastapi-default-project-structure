"""Reports(Raw SQL 예제) API 통합 테스트 — SCN-RAW-001/002, TEST-002/003.

Raw 집계 SQL 이 실제로 도는지, 결과가 Pydantic DTO 로 검증돼 나가는지, 그리고
조회 경로가 커밋하지 않는지를 본다. SCN-RAW-002(Raw DML 검증)도 여기서 다룬다 —
운영 공개 API 는 아니지만 트랜잭션 규칙은 검증돼야 한다.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
)
from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.reports.models.models import SalesOrder  # noqa: F401  (테이블 등록)
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from main import app

BASE = "/api/v1/reports/sales/daily"

# 같은 날 2건 + 다른 날 1건 + 범위 밖 1건
SEED_ORDERS = [
    ("o1", "alice", "100.00", datetime(2026, 8, 1, 9, 0)),
    ("o2", "bob", "50.50", datetime(2026, 8, 1, 18, 30)),
    ("o3", "alice", "200.00", datetime(2026, 8, 3, 12, 0)),
    ("o4", "carol", "999.00", datetime(2026, 9, 1, 12, 0)),
]


@pytest_asyncio.fixture
async def sales_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        for order_id, customer, amount, created in SEED_ORDERS:
            db_session.add(
                SalesOrder(
                    id=order_id,
                    customer=customer,
                    total_amount=Decimal(amount),
                    created_at=created,
                )
            )
        await db_session.commit()

    yield engine, maker
    await engine.dispose()


@pytest_asyncio.fixture
async def client(sales_engine):
    _, maker = sales_engine
    counter = {"commits": 0}

    async def _override_session():
        async with maker() as db_session:
            original_commit = db_session.commit

            async def _counting_commit(*args, **kwargs):
                counter["commits"] += 1
                return await original_commit(*args, **kwargs)

            db_session.commit = _counting_commit  # type: ignore[method-assign]
            yield db_session

    app.dependency_overrides[get_read_only_db_session] = _override_session
    app.dependency_overrides[get_writer_db_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client, counter
    app.dependency_overrides.clear()


# =============================================================================
# 집계 결과
# =============================================================================
async def test_daily_sales_aggregates_by_day(client):
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-08-01", "end_date": "2026-08-07"}
    )

    body = response.json()
    assert response.status_code == 200, response.text

    # 금액은 Decimal 로 비교한다 — DB 마다 SUM 의 소수 표기가 달라(150.5 / 150.50)
    # 문자열 동등 비교는 방언에 묶인 검사가 된다.
    observed = [
        (item["sales_date"], item["order_count"], Decimal(item["gross_amount"]))
        for item in body["items"]
    ]
    assert observed == [
        ("2026-08-01", 2, Decimal("150.50")),
        ("2026-08-03", 1, Decimal("200.00")),
    ], "매출이 없는 날은 결과에 나타나지 않는다"


async def test_end_date_is_inclusive(client):
    """종료일 당일 주문이 포함돼야 한다 — 반열린 구간 변환의 핵심."""
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-08-03", "end_date": "2026-08-03"}
    )

    body = response.json()
    assert [item["sales_date"] for item in body["items"]] == ["2026-08-03"]
    assert body["items"][0]["order_count"] == 1


async def test_orders_outside_the_range_are_excluded(client):
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-08-01", "end_date": "2026-08-31"}
    )

    dates = [item["sales_date"] for item in response.json()["items"]]
    assert "2026-09-01" not in dates


async def test_empty_range_returns_empty_items(client):
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-01-01", "end_date": "2026-01-31"}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


# =============================================================================
# 오류 경로
# =============================================================================
async def test_reversed_range_is_rejected(client):
    """필드 간 규칙이라 Pydantic 이 아니라 Service 가 잡는다."""
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-08-07", "end_date": "2026-08-01"}
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "REPORT_INVALID_DATE_RANGE"


async def test_excessive_range_is_rejected(client):
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2020-01-01", "end_date": "2026-12-31"}
    )

    assert response.status_code == 422


async def test_malformed_date_returns_422(client):
    http_client, _ = client

    response = await http_client.get(BASE, params={"start_date": "어제", "end_date": "2026-08-01"})

    assert response.status_code == 422


# =============================================================================
# 트랜잭션 경계 (TEST-002)
# =============================================================================
async def test_report_query_does_not_commit(client):
    http_client, counter = client
    counter["commits"] = 0

    await http_client.get(BASE, params={"start_date": "2026-08-01", "end_date": "2026-08-07"})

    assert counter["commits"] == 0, "Raw 조회가 커밋했다 (TX-002 위반)"


# =============================================================================
# SCN-RAW-002 — Raw DML workflow 검증 (운영 공개 API 아님)
# =============================================================================
async def test_raw_dml_reports_affected_rows_and_needs_explicit_commit(sales_engine):
    """Repository 는 execute 까지만 하고, 커밋은 호출자가 명시한다."""
    _, maker = sales_engine

    async with maker() as db_session:
        repository = SalesReportRawRepository(db_session)
        affected = await repository.execute(
            text(
                "UPDATE sales_orders SET total_amount = total_amount + :delta WHERE customer = :customer"
            ),
            {"customer": "alice", "delta": 10},
            query_name="sales_report.test_bump",
        )
        assert affected == 2, "영향받은 행 수를 그대로 돌려줘야 한다"
        await db_session.commit()  # 커밋은 호출자의 명시적 행위다

    async with maker() as db_session:
        total = await SalesReportRawRepository(db_session).fetch_scalar(
            text("SELECT SUM(total_amount) FROM sales_orders WHERE customer = :customer"),
            {"customer": "alice"},
            query_name="sales_report.test_total",
        )
        assert Decimal(str(total)) == Decimal("320.00")


async def test_raw_dml_rolls_back_without_commit(sales_engine):
    """커밋하지 않으면 세션 종료 시 사라진다 — Repository 는 커밋하지 않는다."""
    _, maker = sales_engine

    async with maker() as db_session:
        await SalesReportRawRepository(db_session).execute(
            text("DELETE FROM sales_orders"),
            query_name="sales_report.test_wipe",
        )
        # 커밋하지 않고 세션을 닫는다.

    async with maker() as db_session:
        remaining = await SalesReportRawRepository(db_session).fetch_scalar(
            text("SELECT COUNT(*) FROM sales_orders"),
            query_name="sales_report.test_count",
        )
        assert remaining == len(SEED_ORDERS), "커밋하지 않은 Raw DML 이 반영됐다"


async def test_raw_dml_is_blocked_on_a_read_only_session(sales_engine):
    """read-only 세션에서 Raw DML 은 즉시 실패해야 한다 (RAW-REP-007).

    쓰기 차단은 **라우팅 세션**의 기능이다. ``DB_ROUTER_ENABLED=false`` 인 기본
    설정에서는 단일 엔진 세션이라 차단이 동작하지 않는다(문서화된 동작). 그래서
    여기서는 라우터를 켠 세션을 직접 만들어 계약을 검증한다.
    """
    engine, _ = sales_engine

    routing_maker = create_routing_sessionmaker(
        DatabaseRouter(writer=engine, readers=[], sticky_after_write=True)
    )

    async with routing_maker() as db_session:
        mark_read_only(db_session)
        repository = SalesReportRawRepository(db_session)

        with pytest.raises(ReadOnlyRoutingError):
            await repository.execute(
                text("DELETE FROM sales_orders"),
                query_name="sales_report.test_blocked",
            )

    # 차단됐으므로 데이터는 그대로여야 한다.
    async with routing_maker() as db_session:
        remaining = await SalesReportRawRepository(db_session).fetch_scalar(
            text("SELECT COUNT(*) FROM sales_orders"),
            query_name="sales_report.test_count",
        )
        assert remaining == len(SEED_ORDERS)

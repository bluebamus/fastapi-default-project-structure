"""Reports(Raw SQL 예제) API 통합 테스트 — SCN-RAW-001/002, TEST-002/003.

Raw 집계 SQL 이 실제로 도는지, 결과가 Pydantic DTO 로 검증돼 나가는지, 그리고
조회 경로가 커밋하지 않는지를 본다. SCN-RAW-002(Raw DML 검증)도 여기서 다룬다 —
운영 공개 API 는 아니지만 트랜잭션 규칙은 검증돼야 한다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

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
from app.core.db.session import Base
from app.features.reports.models.models import (  # noqa: F401  (테이블 등록)
    SalesDailySnapshot,
    SalesOrder,
)
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
    _offset_param,
)
from app.features.reports.services.report_service import local_day_bounds
from config import timezone_settings
from main import app
from tests.session_overrides import override_db_sessions

BASE = "/api/v1/reports/sales/daily"

# 시드 시각은 **로컬 영업일**(설정 TIME_ZONE) 기준으로 적는다 — 저장은 UTC 로 되고(ADR-010),
# 리포트는 로컬 날짜로 묶는다. naive 값은 저장 경로에서 거부된다.
LOCAL = timezone_settings.tz

# 같은 날 2건 + 다른 날 1건 + 범위 밖 1건
SEED_ORDERS = [
    ("o1", "alice", "100.00", datetime(2026, 8, 1, 9, 0, tzinfo=LOCAL)),
    ("o2", "bob", "50.50", datetime(2026, 8, 1, 18, 30, tzinfo=LOCAL)),
    ("o3", "alice", "200.00", datetime(2026, 8, 3, 12, 0, tzinfo=LOCAL)),
    ("o4", "carol", "999.00", datetime(2026, 9, 1, 12, 0, tzinfo=LOCAL)),
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

    def _wrap_session(db_session):
        original_commit = db_session.commit

        async def _counting_commit(*args, **kwargs):
            counter["commits"] += 1
            return await original_commit(*args, **kwargs)

        db_session.commit = _counting_commit  # type: ignore[method-assign]

    override_db_sessions(app, maker, _wrap_session)
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
# 동적 정렬 — 식별자 allowlist (RAW-REP-004)
# =============================================================================
async def test_default_sort_is_date_ascending(client):
    """정렬을 지정하지 않으면 일자 오름차순이다."""
    http_client, _ = client

    response = await http_client.get(
        BASE, params={"start_date": "2026-08-01", "end_date": "2026-08-07"}
    )

    dates = [item["sales_date"] for item in response.json()["items"]]
    assert dates == sorted(dates)


async def test_sort_by_gross_amount_descending(client):
    """정렬 키가 SQL 의 ORDER BY 로 실제 반영돼야 한다."""
    http_client, _ = client

    response = await http_client.get(
        BASE,
        params={
            "start_date": "2026-08-01",
            "end_date": "2026-08-07",
            "sort_by": "gross_amount",
            "sort_direction": "desc",
        },
    )

    assert response.status_code == 200, response.text
    amounts = [Decimal(item["gross_amount"]) for item in response.json()["items"]]
    assert amounts == [Decimal("200.00"), Decimal("150.50")]


async def test_sort_direction_is_case_insensitive(client):
    """``DESC``/``desc`` 를 모두 받는다 — 방향은 값이 아니라 코드가 확정한다."""
    http_client, _ = client

    params = {
        "start_date": "2026-08-01",
        "end_date": "2026-08-07",
        "sort_by": "sales_date",
        "sort_direction": "DESC",
    }
    response = await http_client.get(BASE, params=params)

    dates = [item["sales_date"] for item in response.json()["items"]]
    assert dates == ["2026-08-03", "2026-08-01"]


@pytest.mark.parametrize(
    "params",
    [
        {"sort_by": "customer"},  # 존재하지만 허용 목록 밖
        {"sort_by": "nope"},  # 존재하지도 않음
        {"sort_direction": "sideways"},
    ],
)
async def test_sort_outside_the_allowlist_is_rejected(client, params):
    """허용 목록 밖 정렬은 422 다 — SQL 에 도달하기 전에 막힌다."""
    http_client, _ = client

    response = await http_client.get(
        BASE,
        params={"start_date": "2026-08-01", "end_date": "2026-08-07", **params},
    )

    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == "REPORT_INVALID_SORT"


async def test_sort_injection_attempt_is_rejected(client):
    """ORDER BY 자리에 SQL 을 밀어 넣으려는 시도는 키 조회 단계에서 실패한다.

    이 검사가 의미 있는 이유는 ORDER BY 가 이 프로젝트에서 **유일하게 f-string
    으로 조립되는 자리**이기 때문이다. 값이 아니라 allowlist 결과만 들어간다는
    계약이 깨지면 여기서 드러난다.
    """
    http_client, _ = client

    response = await http_client.get(
        BASE,
        params={
            "start_date": "2026-08-01",
            "end_date": "2026-08-07",
            "sort_by": "sales_date; DROP TABLE sales_orders--",
        },
    )

    assert response.status_code == 422
    assert response.json()["error_code"] == "REPORT_INVALID_SORT"

    # 테이블이 살아 있어야 한다.
    healthy = await http_client.get(
        BASE, params={"start_date": "2026-08-01", "end_date": "2026-08-07"}
    )
    assert healthy.status_code == 200
    assert healthy.json()["items"], "정렬 거부 후 테이블이 사라졌다"


async def test_repository_allowlist_holds_without_the_view(sales_engine):
    """Repository 를 직접 불러도 같은 제약이 걸린다 (HTTP 계층 밖).

    View 의 쿼리 파라미터에 enum 을 박는 것만으로는 부족하다 — Celery 태스크나
    스크립트가 Repository 를 직접 부르면 그 검증을 우회하기 때문이다.
    """
    _, maker = sales_engine

    async with maker() as db_session:
        repository = SalesReportRawRepository(db_session)

        with pytest.raises(ValueError):
            await repository.daily_sales(
                start_at=datetime(2026, 8, 1, tzinfo=LOCAL),
                end_at=datetime(2026, 8, 8, tzinfo=LOCAL),
                tz_offset=timedelta(hours=9),
                sort_by="customer",
            )


# =============================================================================
# Raw 쓰기 — 스냅샷 적재 (SCN-RAW-003)
# =============================================================================
SNAPSHOTS = "/api/v1/reports/sales/daily/snapshots"
LOAD_RANGE = {"start_date": "2026-08-01", "end_date": "2026-08-07"}


async def _snapshot_rows(maker):
    """스냅샷 테이블을 Raw 로 읽어 (일자, 주문수, 매출) 목록을 돌려준다."""
    async with maker() as db_session:
        result = await db_session.execute(
            text(
                "SELECT sales_date, order_count, gross_amount "
                "FROM sales_daily_snapshots ORDER BY sales_date"
            )
        )
        return [(str(row[0]), row[1], Decimal(str(row[2]))) for row in result.all()]


async def test_snapshot_load_writes_aggregated_rows(client, sales_engine):
    """INSERT ... SELECT 가 집계 결과를 그대로 적재한다."""
    http_client, _ = client
    _, maker = sales_engine

    response = await http_client.post(SNAPSHOTS, json=LOAD_RANGE)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deleted"] == 0, "첫 적재에는 지울 것이 없다"
    assert body["inserted"] == 2, "매출이 있었던 날만 행이 된다"

    assert await _snapshot_rows(maker) == [
        ("2026-08-01", 2, Decimal("150.50")),
        ("2026-08-03", 1, Decimal("200.00")),
    ]


async def test_snapshot_load_is_idempotent(client, sales_engine):
    """같은 기간을 두 번 적재해도 결과가 같다 — DELETE 후 INSERT 이기 때문이다."""
    http_client, _ = client
    _, maker = sales_engine

    first = await http_client.post(SNAPSHOTS, json=LOAD_RANGE)
    after_first = await _snapshot_rows(maker)

    second = await http_client.post(SNAPSHOTS, json=LOAD_RANGE)

    assert second.status_code == 200, second.text
    assert second.json()["deleted"] == first.json()["inserted"], "두 번째는 기존 행을 지운다"
    assert second.json()["inserted"] == first.json()["inserted"]
    assert await _snapshot_rows(maker) == after_first, "행이 두 배가 되면 리포트가 두 배로 보인다"


async def test_snapshot_load_does_not_touch_the_ledger(client, sales_engine):
    """원장은 불변이다 — 적재는 sales_orders 를 읽기만 한다."""
    http_client, _ = client
    _, maker = sales_engine

    async def ledger_snapshot():
        async with maker() as db_session:
            result = await db_session.execute(
                text("SELECT id, customer, total_amount, created_at FROM sales_orders ORDER BY id")
            )
            return [tuple(str(value) for value in row) for row in result.all()]

    before = await ledger_snapshot()
    await http_client.post(SNAPSHOTS, json=LOAD_RANGE)

    assert await ledger_snapshot() == before, "적재가 주문 원장을 건드렸다"


async def test_snapshot_load_commits_exactly_once(client):
    """DELETE·INSERT 두 문장이지만 커밋은 한 번이다 (TX-001)."""
    http_client, counter = client
    counter["commits"] = 0

    response = await http_client.post(SNAPSHOTS, json=LOAD_RANGE)

    assert response.status_code == 200, response.text
    assert counter["commits"] == 1, f"커밋 {counter['commits']}회 — 정확히 1회여야 한다"


async def test_snapshot_load_rolls_back_when_insert_fails(sales_engine):
    """INSERT 가 실패하면 앞선 DELETE 도 함께 사라진다.

    두 문장이 한 트랜잭션이 아니면, 지우기만 하고 끝나 그 기간의 리포트가 **통째로
    비는** 사고가 난다. 커밋 전에는 아무것도 확정되지 않아야 한다.
    """
    _, maker = sales_engine

    # 먼저 정상 적재분을 만들어 둔다(다른 세션에서 커밋).
    async with maker() as db_session:
        repository = SalesReportRawRepository(db_session)
        await repository.insert_daily_snapshots(
            start_at=datetime(2026, 8, 1, tzinfo=LOCAL),
            end_at=datetime(2026, 8, 8, tzinfo=LOCAL),
            tz_offset=LOCAL.utcoffset(datetime(2026, 8, 1)) or timedelta(0),
            generated_at=datetime(2026, 8, 20, 9, 0, tzinfo=LOCAL),
        )
        await db_session.commit()

    async with maker() as db_session:
        repository = SalesReportRawRepository(db_session)
        deleted = await repository.delete_daily_snapshots(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 7)
        )
        assert deleted == 2
        await db_session.rollback()  # INSERT 실패 상황

    async with maker() as db_session:
        remaining = await db_session.execute(text("SELECT COUNT(*) FROM sales_daily_snapshots"))
        assert remaining.scalar() == 2, "커밋 전 DELETE 가 살아남았다"


async def test_snapshot_load_rejects_a_reversed_range(client):
    """기간 규칙은 조회와 적재가 같은 Service 검증을 공유한다."""
    http_client, _ = client

    response = await http_client.post(
        SNAPSHOTS, json={"start_date": "2026-08-07", "end_date": "2026-08-01"}
    )

    assert response.status_code == 422, response.text


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

    쓰기 차단은 ``Session`` 이벤트 리스너가 집행하므로 ``DB_ROUTER_ENABLED`` 와
    무관하게 동작한다. 여기서는 라우터를 켠 구성으로 검증하고, 라우터 off 를 포함한
    두 구성의 대조는 ``tests/core/test_read_only_guard.py`` 가 맡는다.
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


@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        ("9999-12-31", "9999-12-31"),  # end_date + 1일 이 overflow 로 500 이던 값
        ("9998-12-31", "9999-12-31"),
        ("1969-12-31", "1970-01-01"),
    ],
    ids=["date-max", "crosses-max", "before-min"],
)
async def test_dates_outside_the_supported_range_are_422(client, start_date, end_date):
    """날짜 범위 상·하한(service-hardening ADR-008 ③) — 조회와 적재 모두 같은 규칙."""
    http_client, counter = client
    params = {"start_date": start_date, "end_date": end_date}

    read = await http_client.get(BASE, params=params)
    load = await http_client.post(SNAPSHOTS, json=params)

    for response in (read, load):
        assert response.status_code == 422, response.text
        assert response.json()["error_code"] == "REPORT_INVALID_DATE_RANGE"
    assert counter["commits"] == 0


async def test_boundary_dates_are_accepted(client):
    http_client, _ = client

    upper = await http_client.get(
        BASE, params={"start_date": "9998-12-31", "end_date": "9998-12-31"}
    )
    lower = await http_client.get(
        BASE, params={"start_date": "1970-01-01", "end_date": "1970-01-01"}
    )

    assert upper.status_code == 200, upper.text
    assert lower.status_code == 200, lower.text


# =============================================================================
# 로컬 영업일 · UTC 저장 (service-hardening ADR-010, F-016)
# =============================================================================
def test_local_day_bounds_are_local_midnights_as_utc_instants():
    """로컬 날짜 범위(종료일 포함)는 로컬 자정 두 개의 반열린 구간이다 — UTC 로는 전날 15:00."""
    start_at, end_at = local_day_bounds(date(2026, 1, 2), date(2026, 1, 2), ZoneInfo("Asia/Seoul"))

    assert start_at.astimezone(UTC) == datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
    assert end_at.astimezone(UTC) == datetime(2026, 1, 2, 15, 0, tzinfo=UTC)
    assert start_at.utcoffset() == timedelta(hours=9)


@pytest.mark.parametrize(
    ("dialect_name", "offset", "expected"),
    [
        ("mysql", timedelta(hours=9), "+09:00"),
        ("mysql", timedelta(hours=-5, minutes=-30), "-05:30"),
        ("mysql", timedelta(0), "+00:00"),
        ("sqlite", timedelta(hours=9), "+540 minutes"),
        ("sqlite", timedelta(hours=-5, minutes=-30), "-330 minutes"),
    ],
)
def test_offset_param_matches_each_dialect(dialect_name, offset, expected):
    assert _offset_param(dialect_name, offset) == expected


async def test_order_after_local_midnight_counts_for_the_next_local_day(
    client, sales_engine, monkeypatch
):
    """UTC 2026-01-01 15:30 은 KST 1월 2일 00:30 이다 — 리포트·스냅샷 모두 1월 2일에 묶는다.

    UTC 날짜로 묶으면 1월 1일이 되고, 로컬 자정 경계로 자르지 않으면 범위에서 빠진다.
    """
    from config import timezone_settings as tz_settings

    monkeypatch.setattr(tz_settings, "TIME_ZONE", "Asia/Seoul")
    http_client, _ = client
    _, maker = sales_engine
    async with maker() as db_session:
        db_session.add(
            SalesOrder(
                id="midnight",
                customer="dave",
                total_amount=Decimal("10.00"),
                created_at=datetime(2026, 1, 1, 15, 30, tzinfo=UTC),
            )
        )
        await db_session.commit()

    jan_1 = await http_client.get(
        BASE, params={"start_date": "2026-01-01", "end_date": "2026-01-01"}
    )
    jan_2 = await http_client.get(
        BASE, params={"start_date": "2026-01-02", "end_date": "2026-01-02"}
    )
    load = await http_client.post(
        SNAPSHOTS, json={"start_date": "2026-01-01", "end_date": "2026-01-02"}
    )

    assert jan_1.json()["items"] == []
    assert [(item["sales_date"], item["order_count"]) for item in jan_2.json()["items"]] == [
        ("2026-01-02", 1)
    ]
    assert load.status_code == 200, load.text
    assert await _snapshot_rows(maker) == [("2026-01-02", 1, Decimal("10.00"))]


async def test_snapshot_generated_at_is_rendered_as_utc(client):
    """적재 응답의 ``generated_at`` 은 UTC 오프셋을 가진다(설명 "적재 시각(UTC)")."""
    http_client, _ = client

    response = await http_client.post(SNAPSHOTS, json=LOAD_RANGE)

    generated_at = response.json()["generated_at"]
    assert generated_at.endswith(("Z", "+00:00")), generated_at


async def test_raw_repository_rejects_naive_bounds(sales_engine):
    """Raw 경로도 naive 시각을 받지 않는다 — 드라이버가 오프셋 없이 벽시계만 보내지 않게."""
    from app.core.exception import AppException

    _, maker = sales_engine
    async with maker() as db_session:
        with pytest.raises(AppException):
            await SalesReportRawRepository(db_session).daily_sales(
                start_at=datetime(2026, 8, 1),
                end_at=datetime(2026, 8, 8),
                tz_offset=timedelta(hours=9),
            )

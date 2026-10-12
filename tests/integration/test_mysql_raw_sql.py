"""MySQL 8.4 에서 실제 Raw 집계 SQL 과 migration 체인을 검증한다 (RAW-REP-006).

SQLite 통과만으로 MySQL SQL 을 승인하지 않는다는 것이 이 파일의 존재 이유다.
DATE()·SUM()·NUMERIC 반올림·타임존 처리처럼 방언마다 다른 지점이 여기서 드러난다.
읽기(집계)뿐 아니라 쓰기(``INSERT ... SELECT`` 스냅샷 적재)도 여기서 확인한다.

migration 은 현재 head 까지 올린 뒤 **downgrade → 재-upgrade** 까지 돌려
되돌릴 수 있는 revision 인지 확인한다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.models.types import compare_type
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.services.report_service import ReportService
from config import timezone_settings
from tests.integration.conftest import SYNC_URL

pytestmark = pytest.mark.mysql

# 시드 시각은 로컬 영업일(설정 TIME_ZONE) 기준 — 저장은 UTC, 집계는 로컬 날짜다(ADR-010).
LOCAL = timezone_settings.tz

SEED = [
    ("m1", "alice", "100.00", datetime(2026, 8, 1, 9, 0, tzinfo=LOCAL)),
    ("m2", "bob", "50.50", datetime(2026, 8, 1, 23, 59, 59, tzinfo=LOCAL)),
    ("m3", "alice", "200.25", datetime(2026, 8, 3, 0, 0, 0, tzinfo=LOCAL)),
    ("m4", "carol", "999.00", datetime(2026, 9, 1, 12, 0, tzinfo=LOCAL)),
]


async def _seed(session_maker) -> None:
    async with session_maker() as db_session:
        for order_id, customer, amount, created in SEED:
            db_session.add(
                SalesOrder(
                    id=order_id,
                    customer=customer,
                    total_amount=Decimal(amount),
                    created_at=created,
                )
            )
        await db_session.commit()


async def test_daily_sales_sql_runs_on_mysql(mysql_session_maker):
    """운영에서 실제로 나갈 SQL 이 MySQL 에서 그대로 동작한다."""
    await _seed(mysql_session_maker)

    async with mysql_session_maker() as db_session:
        items = await ReportService(db_session).get_daily_sales(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
        )

    assert [(item.sales_date, item.order_count, item.gross_amount) for item in items] == [
        (date(2026, 8, 1), 2, Decimal("150.50")),
        (date(2026, 8, 3), 1, Decimal("200.25")),
    ]


async def test_day_boundaries_are_exact_on_mysql(mysql_session_maker):
    """23:59:59 와 00:00:00 이 각각 옳은 날짜로 집계된다.

    반열린 구간 변환이 틀리면 경계 주문이 하루 밀리거나 사라진다.
    """
    await _seed(mysql_session_maker)

    async with mysql_session_maker() as db_session:
        items = await ReportService(db_session).get_daily_sales(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
        )

    assert len(items) == 1
    assert items[0].order_count == 2, "23:59:59 주문이 당일 집계에 포함돼야 한다"


async def test_decimal_sum_keeps_scale_on_mysql(mysql_session_maker):
    """NUMERIC(12,2) 합계가 float 오차 없이 유지된다."""
    await _seed(mysql_session_maker)

    async with mysql_session_maker() as db_session:
        total = await SalesReportRawRepository(db_session).fetch_scalar(
            sa.text("SELECT SUM(total_amount) FROM sales_orders"),
            query_name="test.total",
        )

    assert Decimal(str(total)) == Decimal("1349.75")


async def test_bind_parameters_are_not_interpolated_on_mysql(mysql_session_maker):
    """injection 대표 입력이 MySQL 에서도 값으로만 취급된다."""
    await _seed(mysql_session_maker)
    malicious = "alice'; DROP TABLE sales_orders; --"

    async with mysql_session_maker() as db_session:
        rows = await SalesReportRawRepository(db_session).fetch_all(
            sa.text("SELECT * FROM sales_orders WHERE customer = :customer"),
            {"customer": malicious},
            query_name="test.injection",
        )
        assert rows == []

        # 테이블이 살아 있어야 한다.
        remaining = await SalesReportRawRepository(db_session).fetch_scalar(
            sa.text("SELECT COUNT(*) FROM sales_orders"),
            query_name="test.count",
        )
        assert remaining == len(SEED)


# =============================================================================
# migration 체인 (SCN-ORM-001 / SCN-RAW-001)
# =============================================================================
async def test_snapshot_load_runs_on_mysql(mysql_session_maker):
    """``INSERT ... SELECT`` 적재가 MySQL 에서 그대로 동작한다.

    SQLite 에서 통과했다는 사실은 방언 검증이 아니다 — ``DATE()`` 로 만든 값을
    ``DATE`` 컬럼에 넣는 것, ``COALESCE(SUM(...), 0)`` 의 결과 타입이
    ``NUMERIC(14,2)`` 로 들어가는 것 모두 여기서만 확인된다.
    """
    await _seed(mysql_session_maker)

    async with mysql_session_maker() as db_session:
        result = await ReportService(db_session).refresh_daily_snapshots(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
        )
        await db_session.commit()

    assert (result.deleted, result.inserted) == (0, 2)

    async with mysql_session_maker() as db_session:
        rows = (
            await db_session.execute(
                sa.text(
                    "SELECT sales_date, order_count, gross_amount "
                    "FROM sales_daily_snapshots ORDER BY sales_date"
                )
            )
        ).all()

    # 소수 자릿수가 살아 있어야 한다 — float 로 새면 150.5 나 150.49999 가 된다.
    assert [(r[0], r[1], r[2]) for r in rows] == [
        (date(2026, 8, 1), 2, Decimal("150.50")),
        (date(2026, 8, 3), 1, Decimal("200.25")),
    ]


async def test_snapshot_load_is_idempotent_on_mysql(mysql_session_maker):
    """재적재가 MySQL 에서도 멱등이다 — 표준 DELETE+INSERT 만 썼기 때문이다.

    ``ON DUPLICATE KEY UPDATE`` 를 썼다면 이 테스트는 통과해도 SQLite 단위 테스트가
    깨졌을 것이다. 두 방언에서 **같은 문장**이 도는지가 이 검사의 핵심이다.
    """
    await _seed(mysql_session_maker)

    async with mysql_session_maker() as db_session:
        service = ReportService(db_session)
        first = await service.refresh_daily_snapshots(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 7)
        )
        await db_session.commit()

        second = await service.refresh_daily_snapshots(
            start_date=date(2026, 8, 1), end_date=date(2026, 8, 7)
        )
        await db_session.commit()

    assert second.deleted == first.inserted
    assert second.inserted == first.inserted

    async with mysql_session_maker() as db_session:
        total = await db_session.execute(sa.text("SELECT COUNT(*) FROM sales_daily_snapshots"))
        assert total.scalar() == first.inserted, "재적재가 행을 두 배로 만들었다"


def _alembic_config(monkeypatch) -> Config:
    from config import db_settings

    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", SYNC_URL)
    return Config("alembic.ini")


def test_migration_chain_upgrades_downgrades_and_reapplies(monkeypatch, mysql_empty_schema):
    """head → base → head 왕복이 MySQL 에서 성공한다.

    downgrade 를 구현만 해두고 돌려보지 않으면, 롤백이 필요한 순간에야 깨진 것을
    알게 된다.
    """
    config = _alembic_config(monkeypatch)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        tables = set(sa.inspect(engine).get_table_names())
        assert {"catalog_products", "sales_orders"} <= tables

        # 되돌렸다가 다시 올린다.
        command.downgrade(config, "base")
        after_downgrade = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
        assert after_downgrade == set(), f"downgrade 후 남은 테이블: {sorted(after_downgrade)}"

        command.upgrade(config, "head")
        assert {"catalog_products", "sales_orders"} <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrated_mysql_schema_matches_models(monkeypatch, mysql_empty_schema):
    """MySQL 에 적용한 migration 결과가 모델과 일치한다(드리프트 없음)."""
    from app.core.db.models_registry import import_all_models
    from app.core.db.session import Base

    import_all_models()
    config = _alembic_config(monkeypatch)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        with engine.connect() as connection:
            # env.py 와 같은 비교 훅 — 기본 비교는 DATETIME(fsp 0) 과 DATETIME(6) 을 같다고 본다.
            context = MigrationContext.configure(connection, opts={"compare_type": compare_type})
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    # 주석(comment) 차이는 MySQL reflection 특성상 노이즈가 될 수 있어 구조 차이만 본다.
    structural = [
        entry
        for entry in diff
        if not (isinstance(entry, tuple) and entry and "comment" in str(entry[0]))
    ]
    assert structural == [], f"MySQL migration 결과와 모델이 다르다: {structural}"


# =============================================================================
# UTC 저장 (service-hardening ADR-010, F-016)
# =============================================================================
async def test_order_after_local_midnight_counts_for_the_next_local_day_on_mysql(
    mysql_session_maker, monkeypatch
):
    """UTC 2026-01-01 15:30 = KST 1월 2일 00:30 → 리포트·스냅샷 모두 1월 2일(로컬)."""
    monkeypatch.setattr(timezone_settings, "TIME_ZONE", "Asia/Seoul")
    async with mysql_session_maker() as db_session:
        db_session.add(
            SalesOrder(
                id="midnight",
                customer="dave",
                total_amount=Decimal("10.00"),
                created_at=datetime(2026, 1, 1, 15, 30, tzinfo=UTC),
            )
        )
        await db_session.commit()

    async with mysql_session_maker() as db_session:
        service = ReportService(db_session)
        jan_1 = await service.get_daily_sales(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)
        )
        jan_2 = await service.get_daily_sales(
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 2)
        )
        await service.refresh_daily_snapshots(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 2)
        )
        await db_session.commit()

    assert jan_1 == []
    assert [(item.sales_date, item.order_count) for item in jan_2] == [(date(2026, 1, 2), 1)]

    async with mysql_session_maker() as db_session:
        rows = (
            await db_session.execute(
                sa.text("SELECT sales_date, order_count FROM sales_daily_snapshots")
            )
        ).all()
    assert [(r[0], r[1]) for r in rows] == [(date(2026, 1, 2), 1)]


async def test_datetime6_roundtrip_keeps_microseconds_and_returns_utc_on_mysql(
    mysql_session_maker,
):
    """``DATETIME(6)`` 은 마이크로초를 지키고, 읽은 값은 UTC aware 다. DB 에는 UTC 벽시계가 있다."""
    kst_value = datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=LOCAL)
    async with mysql_session_maker() as db_session:
        db_session.add(
            SalesOrder(
                id="micro", customer="erin", total_amount=Decimal("1.00"), created_at=kst_value
            )
        )
        await db_session.commit()

    async with mysql_session_maker() as db_session:
        loaded = await db_session.get(SalesOrder, "micro")
        stored = (
            await db_session.execute(
                sa.text("SELECT created_at FROM sales_orders WHERE id = 'micro'")
            )
        ).scalar_one()

    assert loaded is not None
    assert loaded.created_at == kst_value
    assert loaded.created_at.tzinfo is UTC
    assert loaded.created_at.microsecond == 123456
    assert stored == kst_value.astimezone(UTC).replace(tzinfo=None)


def _column_precision(connection, table: str, column: str) -> int:
    return connection.execute(
        sa.text(
            "SELECT DATETIME_PRECISION FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).scalar_one()


def test_utc_revision_converts_existing_kst_values(monkeypatch, mysql_empty_schema):
    """이전 head 에서 KST 로 적힌 값이 리비전 후 UTC 가 되고, downgrade 가 되돌린다.

    값은 Raw SQL 로 넣는다 — 이전 스키마 시점의 데이터를 그대로 흉내 내야 하므로 현재 모델
    (UTCDateTime)을 거치면 안 된다.
    """
    config = _alembic_config(monkeypatch)
    command.downgrade(config, "base")
    command.upgrade(config, "e5f7a9b1c4d5")

    engine = sa.create_engine(SYNC_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO sales_orders (id, customer, total_amount, created_at) "
                    "VALUES ('legacy', 'kim', 1.00, '2026-01-02 00:30:00')"
                )
            )
            assert _column_precision(connection, "sales_orders", "created_at") == 0

        command.upgrade(config, "a7c9e1f3b5d6")
        with engine.connect() as connection:
            stored = connection.execute(
                sa.text("SELECT created_at FROM sales_orders WHERE id = 'legacy'")
            ).scalar_one()
            assert stored == datetime(2026, 1, 1, 15, 30, 0)
            assert _column_precision(connection, "sales_orders", "created_at") == 6
            comment = connection.execute(
                sa.text(
                    "SELECT COLUMN_COMMENT FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sales_daily_snapshots' "
                    "AND COLUMN_NAME = 'generated_at'"
                )
            ).scalar_one()
            assert comment.startswith("적재 시각"), "MODIFY 가 comment 를 지웠다"

        command.downgrade(config, "e5f7a9b1c4d5")
        with engine.connect() as connection:
            stored = connection.execute(
                sa.text("SELECT created_at FROM sales_orders WHERE id = 'legacy'")
            ).scalar_one()
            assert stored == datetime(2026, 1, 2, 0, 30, 0)
            assert _column_precision(connection, "sales_orders", "created_at") == 0
    finally:
        engine.dispose()

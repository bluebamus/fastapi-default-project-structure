"""MySQL 8.4 에서 실제 Raw 집계 SQL 과 migration 체인을 검증한다 (RAW-REP-006).

SQLite 통과만으로 MySQL SQL 을 승인하지 않는다는 것이 이 파일의 존재 이유다.
DATE()·SUM()·NUMERIC 반올림·타임존 처리처럼 방언마다 다른 지점이 여기서 드러난다.

migration 은 현재 head 까지 올린 뒤 **downgrade → 재-upgrade** 까지 돌려
되돌릴 수 있는 revision 인지 확인한다.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.services.report_service import ReportService
from tests.integration.conftest import SYNC_URL

pytestmark = pytest.mark.mysql

SEED = [
    ("m1", "alice", "100.00", datetime(2026, 8, 1, 9, 0)),
    ("m2", "bob", "50.50", datetime(2026, 8, 1, 23, 59, 59)),
    ("m3", "alice", "200.25", datetime(2026, 8, 3, 0, 0, 0)),
    ("m4", "carol", "999.00", datetime(2026, 9, 1, 12, 0)),
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
            diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()

    # 주석(comment) 차이는 MySQL reflection 특성상 노이즈가 될 수 있어 구조 차이만 본다.
    structural = [
        entry
        for entry in diff
        if not (isinstance(entry, tuple) and entry and "comment" in str(entry[0]))
    ]
    assert structural == [], f"MySQL migration 결과와 모델이 다르다: {structural}"

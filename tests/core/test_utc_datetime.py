"""UTC 저장 시각 타입 — ``UTCDateTime``·``utc_now``·Alembic 훅 (service-hardening ADR-010, F-016).

DB 에는 UTC 벽시계를, 응용에는 UTC aware 값을. naive 값은 저장 경로에서 거부한다 —
KST 벽시계가 오프셋 없이 저장돼 "(UTC)" 라는 설명과 어긋났던 것이 검수 R-05 다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.orm import Session

from app.core.models.types import UTCDateTime, compare_type, render_item
from config import timezone_settings

KST = ZoneInfo("Asia/Seoul")


# =============================================================================
# bind / result
# =============================================================================
def test_bind_converts_kst_aware_to_utc_naive():
    value = datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST)

    bound = UTCDateTime().process_bind_param(value, mysql.dialect())

    assert bound == datetime(2026, 1, 1, 15, 30, 0, 123456)
    assert bound is not None and bound.tzinfo is None


def test_bind_rejects_naive():
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 1, 9, 0), mysql.dialect())


def test_result_attaches_utc():
    loaded = UTCDateTime().process_result_value(datetime(2026, 1, 1, 15, 30), mysql.dialect())

    assert loaded == datetime(2026, 1, 1, 15, 30, tzinfo=UTC)
    assert loaded is not None and loaded.utcoffset() == timedelta(0)


def test_none_passes_through_both_ways():
    assert UTCDateTime().process_bind_param(None, mysql.dialect()) is None
    assert UTCDateTime().process_result_value(None, mysql.dialect()) is None


def test_mysql_column_is_datetime6_and_others_plain_datetime():
    """MySQL 은 마이크로초(fsp 6) — 기본 ``DATETIME`` 은 소수 초를 반올림한다."""
    assert str(UTCDateTime().compile(dialect=mysql.dialect())) == "DATETIME(6)"
    assert str(UTCDateTime().compile(dialect=sqlite.dialect())) == "DATETIME"


def test_utc_now_is_aware_utc():
    now = timezone_settings.utc_now()

    assert now.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - now) < timedelta(seconds=5)


# =============================================================================
# SQLite 왕복 · 모델 기본값
# =============================================================================
def test_sqlite_roundtrip_keeps_microseconds_and_returns_utc():
    metadata = sa.MetaData()
    table = sa.Table(
        "stamps",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", UTCDateTime(), nullable=False),
    )
    engine = sa.create_engine("sqlite://")
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(
                table.insert().values(id=1, at=datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST))
            )
            loaded = connection.execute(sa.select(table.c.at)).scalar_one()
            stored = connection.execute(sa.text("SELECT at FROM stamps")).scalar_one()
    finally:
        engine.dispose()

    assert loaded == datetime(2026, 1, 1, 15, 30, 0, 123456, tzinfo=UTC)
    assert loaded.tzinfo is UTC
    # DB 에는 UTC 벽시계가 들어간다(KST 00:30 이 아니라 UTC 15:30).
    assert stored == "2026-01-01 15:30:00.123456"


def test_model_default_is_aware_utc():
    """``CreatedAtMixin`` 의 기본값은 UTC aware 이고, 다시 읽어도 UTC aware 다."""
    from app.features.reports.models.models import SalesOrder

    engine = sa.create_engine("sqlite://")
    SalesOrder.metadata.create_all(engine, tables=[SalesOrder.__table__])
    try:
        with Session(engine) as session:
            order = SalesOrder(customer="alice", total_amount=Decimal("1.00"))
            session.add(order)
            session.commit()
            order_id = order.id

        with Session(engine) as session:
            loaded = session.get(SalesOrder, order_id)
            assert loaded is not None
            created_at = loaded.created_at
    finally:
        engine.dispose()

    assert created_at.utcoffset() == timedelta(0)
    assert abs(datetime.now(UTC) - created_at) < timedelta(seconds=5)


# =============================================================================
# Alembic 훅 (migrations/env.py 가 넘긴다)
# =============================================================================
def _context(dialect) -> SimpleNamespace:
    return SimpleNamespace(dialect=dialect)


def test_compare_type_flags_mysql_datetime_without_microseconds():
    """DB 가 ``DATETIME``(fsp 0)이면 드리프트다 — Alembic 기본 비교는 이것을 놓친다."""
    ctx = _context(mysql.dialect())

    assert compare_type(ctx, None, None, mysql.DATETIME(), UTCDateTime()) is True
    assert compare_type(ctx, None, None, mysql.DATETIME(fsp=6), UTCDateTime()) is False


def test_compare_type_defers_elsewhere():
    assert (
        compare_type(_context(sqlite.dialect()), None, None, sa.DATETIME(), UTCDateTime()) is None
    )
    assert compare_type(_context(mysql.dialect()), None, None, sa.String(10), sa.String(20)) is None


def test_render_item_writes_an_app_free_equivalent_type():
    autogen = SimpleNamespace(imports=set())

    rendered = render_item("type", UTCDateTime(), autogen)

    assert isinstance(rendered, str)
    assert "from sqlalchemy.dialects import mysql" in autogen.imports
    equivalent = eval(rendered, {"sa": sa, "mysql": mysql})  # noqa: S307 - 테스트가 만든 문자열
    assert str(equivalent.compile(dialect=mysql.dialect())) == "DATETIME(6)"
    assert str(equivalent.compile(dialect=sqlite.dialect())) == "DATETIME"
    assert render_item("type", sa.String(10), autogen) is False

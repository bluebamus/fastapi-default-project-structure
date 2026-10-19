"""관리 목록 날짜 필터 ``LocalDateFilter`` — 로컬 자정 경계·연산·잘못된 입력 (security-ops-hardening ADR-005).

실제 SQLite 와 ``UTCDateTime`` 컬럼(접속 로그)으로 질의해 본다. 시간대는 Asia/Seoul(UTC+9)로 고정한다.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.admin_filters import LocalDateFilter
from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog

SEOUL = ZoneInfo("Asia/Seoul")
# 2026-10-19 00:00 KST == 2026-10-18 15:00 UTC
MIDNIGHT = datetime(2026, 10, 19, tzinfo=SEOUL)
ROWS = {
    "prev-day-last-second": MIDNIGHT - timedelta(seconds=1),
    "midnight": MIDNIGHT,
    "next-day-last-second": MIDNIGHT + timedelta(days=1, seconds=-1),
    "next-day-midnight": MIDNIGHT + timedelta(days=1),
    # 기간 필터 경계(2026-10-19~2026-10-20): 종료일 23:59:59.999999 포함, 그다음 자정 제외.
    "end-day-last-microsecond": MIDNIGHT + timedelta(days=2, microseconds=-1),
    "after-end-midnight": MIDNIGHT + timedelta(days=2),
}


def _filter() -> LocalDateFilter:
    return LocalDateFilter(
        UserAccessLog.created_at,
        tz=SEOUL,
        clock=lambda: datetime(2026, 10, 19, 1, 0, tzinfo=UTC),  # KST 10:00
    )


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        for name, created_at in ROWS.items():
            db_session.add(
                UserAccessLog(
                    ip_address="127.0.0.1",
                    request_path=f"/{name}",
                    request_method="GET",
                    created_at=created_at,
                )
            )
        await db_session.commit()
        yield db_session
    await engine.dispose()


async def _paths(session, operation: str, value: str) -> set[str]:
    query = await _filter().get_filtered_query(
        select(UserAccessLog), operation, value, UserAccessLog
    )
    rows = (await session.execute(query)).scalars().all()
    return {row.request_path.lstrip("/") for row in rows}


def test_local_midnight_becomes_utc_aware():
    start = _filter().day_start(MIDNIGHT.date())
    assert start == datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
    assert start.tzinfo is UTC


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("on", {"midnight", "next-day-last-second"}),
        (
            "on_or_after",
            {
                "midnight",
                "next-day-last-second",
                "next-day-midnight",
                "end-day-last-microsecond",
                "after-end-midnight",
            },
        ),
        ("before", {"prev-day-last-second"}),
    ],
)
async def test_operations_use_local_midnight_boundaries(session, operation, expected):
    assert await _paths(session, operation, "2026-10-19") == expected


@pytest.mark.parametrize("value", ["2026-10-32", "19-10-2026", "2026/10/19", "", "9999-12-31"])
async def test_bad_input_is_ignored_with_warning(session, caplog, value):
    with caplog.at_level(logging.WARNING):
        paths = await _paths(session, "on", value)
    assert paths == set(ROWS)
    assert any("날짜 필터 입력 무시" in r.getMessage() for r in caplog.records)


async def test_unknown_operation_is_ignored(session):
    assert await _paths(session, "equals", "2026-10-19") == set(ROWS)


def test_operation_options_and_quick_ranges():
    date_filter = _filter()
    assert [op for op, _ in date_filter.get_operation_options_for_model(UserAccessLog)] == [
        "on",
        "on_or_after",
        "before",
        "between",
    ]
    assert date_filter.quick_ranges() == [
        ("오늘", "on", "2026-10-19"),
        ("최근 7일", "on_or_after", "2026-10-13"),
        ("최근 30일", "on_or_after", "2026-09-20"),
    ]
    assert date_filter.parameter_name == "created_at"
    assert date_filter.has_operator is True


# =============================================================================
# 기간 (admin-session-hardening ADR-005)
# =============================================================================
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "2026-10-19~2026-10-20",
            {"midnight", "next-day-last-second", "next-day-midnight", "end-day-last-microsecond"},
        ),
        ("2026-10-19~2026-10-19", {"midnight", "next-day-last-second"}),
        (
            " 2026-10-20 ~ ",
            {"next-day-midnight", "end-day-last-microsecond", "after-end-midnight"},
        ),
        ("~2026-10-18", {"prev-day-last-second"}),
    ],
    ids=["two-days-inclusive", "one-day", "start-only", "end-only"],
)
async def test_between_includes_both_ends_in_local_days(session, value, expected):
    assert await _paths(session, "between", value) == expected


@pytest.mark.parametrize(
    "value",
    ["2026-10-20~2026-10-19", "2026-10-19", "~", "", "2026-10-32~", "~2026/10/19", "~9999-12-31"],
    ids=["reversed", "no-separator", "both-empty", "empty", "bad-start", "bad-end", "overflow"],
)
async def test_bad_range_is_ignored_with_warning(session, caplog, value):
    with caplog.at_level(logging.WARNING):
        paths = await _paths(session, "between", value)
    assert paths == set(ROWS)
    assert any("날짜 필터 입력 무시" in r.getMessage() for r in caplog.records)


def test_date_range_converts_local_bounds_to_utc():
    start, end = _filter().date_range("2026-10-19~2026-10-20")
    assert start == datetime(2026, 10, 18, 15, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    assert _filter().date_range("2026-10-19~") == (start, None)
    assert _filter().date_range("~2026-10-20") == (None, end)


def test_date_range_follows_dst():
    """미국 동부 2026-03-08(DST 시작, 23시간) — 하루 범위가 23시간, 11-01(종료)은 25시간."""
    new_york = LocalDateFilter(UserAccessLog.created_at, tz=ZoneInfo("America/New_York"))
    start, end = new_york.date_range("2026-03-08~2026-03-08")
    assert start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 9, 4, 0, tzinfo=UTC)
    start, end = new_york.date_range("2026-11-01~2026-11-01")
    assert end - start == timedelta(hours=25)

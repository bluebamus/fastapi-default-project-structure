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
        ("on_or_after", {"midnight", "next-day-last-second", "next-day-midnight"}),
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
    ]
    assert date_filter.quick_ranges() == [
        ("오늘", "on", "2026-10-19"),
        ("최근 7일", "on_or_after", "2026-10-13"),
        ("최근 30일", "on_or_after", "2026-09-20"),
    ]
    assert date_filter.parameter_name == "created_at"
    assert date_filter.has_operator is True

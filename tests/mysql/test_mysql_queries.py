"""MySQL 에서만 드러나는 쿼리 동작 — 드라이버 오류 코드 번역·읽기 전용 경로·CONVERT_TZ 집계."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import ForeignKey, String, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import session as session_module
from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
)
from app.core.db.session import Base
from app.core.exception import ConflictException, DuplicateException, ValidationException
from app.core.repositories.raw_repository_base import RawRepositoryBase
from app.core.repositories.repository_base import BaseRepository
from app.features.reports.models.models import SalesDailySnapshot, SalesOrder
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository

KST = timezone(timedelta(hours=9))


class _Base(DeclarativeBase):
    pass


class Parent(_Base):
    __tablename__ = "mysql_parents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Child(_Base):
    __tablename__ = "mysql_children"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("mysql_parents.id"), nullable=False)


class ParentRepository(BaseRepository[Parent]):  # type: ignore[type-var]
    model = Parent


class ChildRepository(BaseRepository[Child]):  # type: ignore[type-var]
    model = Child


class ParentRawRepository(RawRepositoryBase):
    async def delete(self, *, pk: str) -> int:
        return await self.execute(
            text("DELETE FROM mysql_parents WHERE id = :id"), {"id": pk}, query_name="parent.delete"
        )


@pytest_asyncio.fixture
async def tables(mysql_engine):
    async with mysql_engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)


# =============================================================================
# 드라이버 오류 코드 → 앱 예외(HTTP 상태) — 단위 테스트는 가짜 예외, 여기는 실제 MySQL 코드
# =============================================================================
async def test_duplicate_key_1062_is_409_duplicate(tables, mysql_sessionmaker):
    async with mysql_sessionmaker() as session:
        repository = ParentRepository(session)
        await repository.create({"id": "p1", "name": "dup"})
        with pytest.raises(DuplicateException) as exc_info:
            await repository.create({"id": "p2", "name": "dup"})
    assert (exc_info.value.status_code, exc_info.value.error_code) == (409, "DUPLICATE")


async def test_missing_reference_1452_is_422(tables, mysql_sessionmaker):
    async with mysql_sessionmaker() as session:
        with pytest.raises(ValidationException) as exc_info:
            await ChildRepository(session).create({"id": "c1", "parent_id": "없는-부모"})
    assert exc_info.value.status_code == 422


async def test_deleting_referenced_row_1451_is_409_conflict(tables, mysql_sessionmaker):
    """Raw 계층도 같은 번역 표를 쓴다 — 참조 중인 행 삭제는 DUPLICATE 가 아닌 CONFLICT."""
    async with mysql_sessionmaker() as session:
        await ParentRepository(session).create({"id": "p1", "name": "parent"})
        await ChildRepository(session).create({"id": "c1", "parent_id": "p1"})
        with pytest.raises(ConflictException) as exc_info:
            await ParentRawRepository(session).delete(pk="p1")
    assert (exc_info.value.status_code, exc_info.value.error_code) == (409, "CONFLICT")


# =============================================================================
# 읽기 전용 경로
# =============================================================================
async def test_read_only_session_rejects_writes_before_they_reach_mysql(tables, mysql_sessionmaker):
    """aiomysql 세션에서도 ORM flush·Raw INSERT 가 거부되고, 서버에는 아무것도 남지 않는다."""
    async with mysql_sessionmaker() as session:
        mark_read_only(session)
        assert (await session.execute(select(func.count()).select_from(Parent))).scalar_one() == 0
        session.add(Parent(id="p1", name="x"))
        with pytest.raises(ReadOnlyRoutingError):
            await session.flush()
        await session.rollback()
        with pytest.raises(ReadOnlyRoutingError):
            await session.execute(text("INSERT INTO mysql_parents (id, name) VALUES ('p2', 'y')"))

    async with mysql_sessionmaker() as session:
        assert (await session.execute(select(func.count()).select_from(Parent))).scalar_one() == 0


async def test_routing_reads_from_reader_and_keeps_writes_on_writer(
    tables, mysql_url, mysql_engine
):
    """writer/reader 엔진을 둔 라우팅 세션이 실제 MySQL 연결에서 성립한다.

    증명하는 것: 쓰기 세션의 커밋이 writer 엔진으로 가고, 읽기 전용 세션의 SELECT 가 reader
    엔진으로 가며, 그 세션의 쓰기는 거부된다. reader 는 **같은 서버**를 가리키는 별도 엔진이다.
    증명하지 못하는 것: 복제 지연·replica 의 ``read_only``·replica 장애 시 writer 재시도 —
    CI 에는 복제본이 없다.
    """
    reader_engine = session_module._create_read_engine(mysql_url)
    try:
        maker = create_routing_sessionmaker(
            DatabaseRouter(writer=mysql_engine, readers=[reader_engine], sticky_after_write=True)
        )
        async with maker() as session:
            session.add(Parent(id="p1", name="written"))
            await session.commit()
            assert session.get_bind() is mysql_engine.sync_engine

        async with maker() as session:
            mark_read_only(session)
            names = (await session.execute(select(Parent.name))).scalars().all()
            assert session.get_bind(clause=select(Parent)) is reader_engine.sync_engine
            session.add(Parent(id="p2", name="blocked"))
            with pytest.raises(ReadOnlyRoutingError):
                await session.flush()
        assert names == ["written"]
    finally:
        await reader_engine.dispose()


# =============================================================================
# MySQL 전용 SQL — CONVERT_TZ 로 UTC 저장 시각을 로컬 영업일로 묶는다
# =============================================================================
async def _seed_orders(mysql_engine, mysql_sessionmaker):
    async with mysql_engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[SalesOrder.__table__, SalesDailySnapshot.__table__],
        )
    async with mysql_sessionmaker() as session:
        session.add_all(
            [
                # KST 1월 1일 23:59:59.999999 — 소수 초가 반올림되면 1월 2일로 넘어간다.
                SalesOrder(
                    id="late",
                    customer="a",
                    total_amount=Decimal("10.00"),
                    created_at=datetime(2026, 1, 1, 14, 59, 59, 999999, tzinfo=UTC),
                ),
                # UTC 1월 1일 15:30 = KST 1월 2일 00:30.
                SalesOrder(
                    id="midnight",
                    customer="b",
                    total_amount=Decimal("5.50"),
                    created_at=datetime(2026, 1, 1, 15, 30, tzinfo=UTC),
                ),
            ]
        )
        await session.commit()


async def test_daily_sales_groups_by_local_date_with_convert_tz(mysql_engine, mysql_sessionmaker):
    await _seed_orders(mysql_engine, mysql_sessionmaker)

    async with mysql_sessionmaker() as session:
        rows = await SalesReportRawRepository(session).daily_sales(
            start_at=datetime(2026, 1, 1, tzinfo=KST),
            end_at=datetime(2026, 1, 3, tzinfo=KST),
            tz_offset=timedelta(hours=9),
        )

    assert [(r["sales_date"], r["order_count"], r["gross_amount"]) for r in rows] == [
        (date(2026, 1, 1), 1, Decimal("10.00")),
        (date(2026, 1, 2), 1, Decimal("5.50")),
    ]


async def test_snapshot_insert_select_uses_the_same_local_date(mysql_engine, mysql_sessionmaker):
    await _seed_orders(mysql_engine, mysql_sessionmaker)

    async with mysql_sessionmaker() as session:
        inserted = await SalesReportRawRepository(session).insert_daily_snapshots(
            start_at=datetime(2026, 1, 1, tzinfo=KST),
            end_at=datetime(2026, 1, 3, tzinfo=KST),
            tz_offset=timedelta(hours=9),
            generated_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        await session.commit()

    async with mysql_sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT sales_date, order_count, gross_amount "
                    "FROM sales_daily_snapshots ORDER BY sales_date"
                )
            )
        ).all()

    assert inserted == 2
    assert [tuple(r) for r in rows] == [
        (date(2026, 1, 1), 1, Decimal("10.00")),
        (date(2026, 1, 2), 1, Decimal("5.50")),
    ]

"""MySQL 에서만 드러나는 스키마 동작 — 마이그레이션·DATETIME(6)·인증 플러그인."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.core.db.models_registry import import_all_models
from app.core.db.session import Base
from app.core.models.types import compare_type
from app.features.reports.models.models import SalesOrder
from config import db_settings

KST = timezone(timedelta(hours=9))


async def test_baseline_upgrade_matches_models_and_downgrade_is_clean(mysql_url, monkeypatch):
    """빈 MySQL 에 ``upgrade head`` → 모델과 diff 없음(DATETIME(6) 비교 포함) → ``downgrade base``."""
    sync_url = mysql_url.set(drivername="mysql+pymysql")
    # env.py 는 db_settings.ALEMBIC_URL 을 읽는다. fileConfig 는 프로세스 로깅을 바꾸므로 무력화한다.
    monkeypatch.setattr(
        db_settings, "ALEMBIC_DATABASE_URL", sync_url.render_as_string(hide_password=False)
    )
    monkeypatch.setattr("logging.config.fileConfig", lambda *args, **kwargs: None)
    import_all_models()
    alembic_cfg = Config("alembic.ini")
    engine = sa.create_engine(sync_url, poolclass=NullPool)
    try:
        command.upgrade(alembic_cfg, "head")
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={"compare_type": compare_type})
            diff = compare_metadata(context, Base.metadata)
        assert diff == [], f"MySQL 마이그레이션 결과와 모델이 다르다: {diff}"

        command.downgrade(alembic_cfg, "base")
        assert set(sa.inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()


async def test_utc_datetime_column_is_datetime_6(mysql_engine):
    """``UTCDateTime`` 은 MySQL 에서 DATETIME(6) 으로 만들어진다 — 기본 DATETIME 은 소수 초를 반올림한다."""
    async with mysql_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
        row = (
            await connection.execute(
                text(
                    "SELECT DATA_TYPE, DATETIME_PRECISION FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sales_orders' "
                    "AND COLUMN_NAME = 'created_at'"
                )
            )
        ).one()
    assert (row[0].lower(), row[1]) == ("datetime", 6)


async def test_utc_datetime_round_trips_microseconds_as_utc(mysql_engine, mysql_sessionmaker):
    """KST 자정 직전(마이크로초 999999)을 넣으면 같은 순간이 UTC aware 로 돌아온다."""
    async with mysql_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
    written = datetime(2026, 1, 1, 23, 59, 59, 999999, tzinfo=KST)
    async with mysql_sessionmaker() as session:
        session.add(
            SalesOrder(id="o1", customer="c", total_amount=Decimal("1.00"), created_at=written)
        )
        await session.commit()

    async with mysql_sessionmaker() as session:
        read = (await session.execute(sa.select(SalesOrder.created_at))).scalar_one()
        raw = (await session.execute(text("SELECT created_at FROM sales_orders"))).scalar_one()

    assert read == written
    assert read.tzinfo is UTC
    assert read.microsecond == 999999
    assert raw == datetime(2026, 1, 1, 14, 59, 59, 999999), "DB 에는 UTC 벽시계가 저장돼야 한다"


async def test_driver_authenticates_with_caching_sha2_password(mysql_engine):
    """MySQL 8 기본 인증(caching_sha2_password)으로 앱 드라이버(aiomysql)가 접속한다.

    TLS 없는 연결의 전체 인증은 RSA 가 필요하다(aiomysql[rsa] → cryptography). 계정은
    ``mysql.user`` 를 읽을 권한이 있어야 한다(CI 는 root).
    """
    async with mysql_engine.connect() as connection:
        plugin = (
            await connection.execute(
                text(
                    "SELECT plugin FROM mysql.user "
                    "WHERE CONCAT(user, '@', host) = CURRENT_USER()"
                )
            )
        ).scalar_one()
    assert plugin == "caching_sha2_password"

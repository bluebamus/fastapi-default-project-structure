"""DB 라우터(읽기/쓰기 분리) 계약 테스트.

실제 두 개의 독립 SQLite 엔진을 writer/reader 로 붙이고, 각 DB 에 서로 다른
'origin' 행을 심어 **어느 서버가 쿼리를 처리했는지**를 결과값으로 증명한다.
(모킹이 아니라 실제 바인딩 동작을 검증한다.)
"""

import pytest
from sqlalchemy import String, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from config import DatabaseSettings


class ProbeBase(DeclarativeBase):
    """테스트 전용 메타데이터 (앱 Base 를 오염시키지 않는다)."""


class Probe(ProbeBase):
    __tablename__ = "routing_probe"

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(16))


async def _make_engine(origin: str) -> AsyncEngine:
    """`origin` 행 하나가 들어있는 독립 in-memory SQLite 엔진을 만든다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 커넥션 1개 유지 → :memory: DB 가 살아있다
    )
    async with engine.begin() as conn:
        await conn.run_sync(ProbeBase.metadata.create_all)
        await conn.execute(insert(Probe).values(id=1, origin=origin))
    return engine


async def _origins(session) -> list[str]:
    result = await session.execute(select(Probe.origin).order_by(Probe.id))
    return list(result.scalars().all())


# =============================================================================
# 라우팅 동작 (투명 라우팅)
# =============================================================================
async def test_select_is_served_by_reader():
    """SELECT 는 replica(reader) 엔진으로 나간다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        assert await _origins(session) == ["reader"]

    await writer.dispose()
    await reader.dispose()


async def test_flush_is_served_by_writer():
    """ORM 쓰기(flush)는 primary(writer) 엔진으로 나간다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        session.add(Probe(id=2, origin="written"))
        await session.flush()
        await session.commit()

    # writer DB 에만 행이 늘어야 한다.
    async with writer.begin() as conn:
        assert len((await conn.execute(select(Probe.origin))).scalars().all()) == 2
    async with reader.begin() as conn:
        assert len((await conn.execute(select(Probe.origin))).scalars().all()) == 1

    await writer.dispose()
    await reader.dispose()


async def test_dml_statement_is_served_by_writer():
    """Core DML(insert/update/delete)도 writer 로 라우팅된다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        await session.execute(insert(Probe).values(id=3, origin="dml"))
        await session.commit()

    async with reader.begin() as conn:
        assert (await conn.execute(select(Probe.origin))).scalars().all() == ["reader"]

    await writer.dispose()
    await reader.dispose()


async def test_read_after_write_sticks_to_writer():
    """쓰기가 발생한 세션의 이후 SELECT 는 writer 로 고정된다(복제 지연 회피)."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        session.add(Probe(id=2, origin="written"))
        await session.flush()
        assert await _origins(session) == ["writer", "written"]

    await writer.dispose()
    await reader.dispose()


async def test_sticky_disabled_returns_to_reader_after_write():
    """sticky_after_write=False 면 쓰기 이후 SELECT 도 reader 로 돌아간다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(
        DatabaseRouter(writer=writer, readers=[reader], sticky_after_write=False)
    )

    async with maker() as session:
        session.add(Probe(id=2, origin="written"))
        await session.flush()
        assert await _origins(session) == ["reader"]
        await session.rollback()

    await writer.dispose()
    await reader.dispose()


async def test_reader_is_pinned_for_session_lifetime():
    """한 세션 안의 여러 SELECT 는 같은 replica 를 재사용한다."""
    writer = await _make_engine("writer")
    readers = [await _make_engine("reader-1"), await _make_engine("reader-2")]
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=readers))

    async with maker() as session:
        first = await _origins(session)
        second = await _origins(session)
        assert first == second

    await writer.dispose()
    for reader in readers:
        await reader.dispose()


async def test_readers_are_round_robined_across_sessions():
    """세션마다 replica 를 라운드로빈으로 분산한다."""
    writer = await _make_engine("writer")
    readers = [await _make_engine("reader-1"), await _make_engine("reader-2")]
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=readers))

    served = []
    for _ in range(4):
        async with maker() as session:
            served.extend(await _origins(session))

    assert served == ["reader-1", "reader-2", "reader-1", "reader-2"]

    await writer.dispose()
    for reader in readers:
        await reader.dispose()


async def test_no_replica_routes_everything_to_writer():
    """replica 가 없으면 읽기도 writer 로 간다(라우터 켜짐 + 복제 꺼짐)."""
    writer = await _make_engine("writer")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[]))

    async with maker() as session:
        assert await _origins(session) == ["writer"]

    await writer.dispose()


# =============================================================================
# 명시적 이스케이프 해치
# =============================================================================
async def test_using_writer_forces_select_to_writer():
    """using_writer() 로 표시한 세션은 SELECT 도 writer 로 보낸다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        using_writer(session)
        assert await _origins(session) == ["writer"]

    await writer.dispose()
    await reader.dispose()


async def test_read_only_session_rejects_writes():
    """읽기 전용으로 표시한 세션에서 쓰기를 시도하면 즉시 실패한다."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    async with maker() as session:
        mark_read_only(session)
        assert await _origins(session) == ["reader"]

        session.add(Probe(id=2, origin="written"))
        with pytest.raises(ReadOnlyRoutingError):
            await session.flush()

    await writer.dispose()
    await reader.dispose()


# =============================================================================
# 설정 (config.DatabaseSettings)
# =============================================================================
def _settings(**overrides) -> DatabaseSettings:
    """`.env` 를 무시하고 순수 기본값 + 오버라이드로 설정을 만든다."""
    return DatabaseSettings(_env_file=None, **overrides)


def test_router_disabled_by_default():
    settings = _settings()
    assert settings.DB_ROUTER_ENABLED is False
    assert settings.DB_REPLICATION_ENABLED is False
    assert settings.routing_mode == "single"
    assert settings.replication_active is False


def test_router_without_replication_is_single_mode():
    settings = _settings(DB_ROUTER_ENABLED=True)
    assert settings.routing_mode == "router-single"
    assert settings.replication_active is False
    assert settings.MYSQL_REPLICA_URLS == []


def test_replication_mode_builds_replica_urls():
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["replica-a", "replica-b:3307"],
    )
    assert settings.routing_mode == "router-replicated"
    assert settings.replication_active is True
    assert settings.MYSQL_REPLICA_URLS == [
        "mysql+aiomysql://root:@replica-a:3306/fastapi_db",
        "mysql+aiomysql://root:@replica-b:3307/fastapi_db",
    ]


def test_replica_hosts_accept_ip_and_domain():
    """replica 는 IP 주소와 도메인 이름을 모두 받는다 (포트 생략 시 기본 포트)."""
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["10.0.0.11", "db-replica.example.com:3307"],
    )
    assert settings.MYSQL_REPLICA_URLS == [
        "mysql+aiomysql://root:@10.0.0.11:3306/fastapi_db",
        "mysql+aiomysql://root:@db-replica.example.com:3307/fastapi_db",
    ]


def test_ipv6_replica_host_must_be_bracketed():
    """IPv6 는 대괄호 표기를 그대로 유지한다 (포트 구분자와 콜론이 섞이지 않도록)."""
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_REPLICA_HOSTS=["[2001:db8::10]:3307", "[::1]"],
    )
    assert settings.MYSQL_REPLICA_URLS == [
        "mysql+aiomysql://root:@[2001:db8::10]:3307/fastapi_db",
        "mysql+aiomysql://root:@[::1]:3306/fastapi_db",
    ]


def test_bare_ipv6_replica_host_is_rejected():
    """대괄호 없는 IPv6 는 깨진 DSN 이 되므로 기동 시점에 거부한다."""
    with pytest.raises(ValueError, match="대괄호"):
        _settings(
            DB_ROUTER_ENABLED=True,
            DB_REPLICATION_ENABLED=True,
            MYSQL_REPLICA_HOSTS=["2001:db8::10"],
        )


def test_empty_replica_host_is_rejected():
    with pytest.raises(ValueError, match="호스트"):
        _settings(
            DB_ROUTER_ENABLED=True,
            DB_REPLICATION_ENABLED=True,
            MYSQL_REPLICA_HOSTS=[":3307"],
        )


def test_primary_host_accepts_ip_and_domain():
    assert _settings(MYSQL_HOST="10.0.0.10").MYSQL_URL.endswith("@10.0.0.10:3306/fastapi_db")
    assert _settings(MYSQL_HOST="db.example.com").MYSQL_URL.endswith(
        "@db.example.com:3306/fastapi_db"
    )


def test_primary_ipv6_host_is_bracketed_in_url():
    """IPv6 primary 도 대괄호로 감싸야 포트와 구분된다 (`@::1:3306` 은 깨진 DSN)."""
    assert _settings(MYSQL_HOST="::1").MYSQL_URL == "mysql+aiomysql://root:@[::1]:3306/fastapi_db"
    assert (
        _settings(MYSQL_HOST="[2001:db8::10]").MYSQL_URL
        == "mysql+aiomysql://root:@[2001:db8::10]:3306/fastapi_db"
    )


def test_replica_credentials_fall_back_to_primary():
    """replica 전용 자격증명을 주지 않으면 primary 값을 재사용한다."""
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_USER="app",
        MYSQL_PASSWORD="pw",  # noqa: S106 - 테스트 픽스처 값
        MYSQL_DATABASE="shop",
        MYSQL_REPLICA_HOSTS=["replica-a"],
    )
    assert settings.MYSQL_REPLICA_URLS == ["mysql+aiomysql://app:pw@replica-a:3306/shop"]


def test_replica_credentials_can_be_overridden():
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_USER="app",
        MYSQL_PASSWORD="pw",  # noqa: S106 - 테스트 픽스처 값
        MYSQL_REPLICA_HOSTS=["replica-a"],
        MYSQL_REPLICA_USER="ro",
        MYSQL_REPLICA_PASSWORD="ro-pw",  # noqa: S106 - 테스트 픽스처 값
    )
    assert settings.MYSQL_REPLICA_URLS == ["mysql+aiomysql://ro:ro-pw@replica-a:3306/fastapi_db"]


def test_replication_without_router_is_rejected():
    """복제만 켜고 라우터를 끈 조합은 기동 시점에 차단한다(fail-fast)."""
    with pytest.raises(ValueError, match="DB_ROUTER_ENABLED"):
        _settings(DB_REPLICATION_ENABLED=True, MYSQL_REPLICA_HOSTS=["replica-a"])


def test_replication_without_replica_hosts_is_rejected():
    with pytest.raises(ValueError, match="MYSQL_REPLICA_HOSTS"):
        _settings(DB_ROUTER_ENABLED=True, DB_REPLICATION_ENABLED=True)


def test_router_disabled_keeps_single_engine_wiring():
    """라우터가 꺼진 기본 설정에서는 세션이 단일 엔진에 직접 바인딩된다."""
    from app.core.db import session as session_module

    assert session_module.read_engines == []
    assert session_module.db_router.replicated is False
    assert session_module.db_router.writer is session_module.engine
    assert session_module.writer_engine is session_module.engine
    # RoutingSession 이 끼어들지 않는다 → 오버헤드·동작 모두 기존 그대로
    assert session_module.AsyncSessionLocal.kw.get("sync_session_class") is None


def test_describe_routing_masks_passwords():
    settings = _settings(
        DB_ROUTER_ENABLED=True,
        DB_REPLICATION_ENABLED=True,
        MYSQL_PASSWORD="super-secret",  # noqa: S106 - 테스트 픽스처 값
        MYSQL_REPLICA_HOSTS=["replica-a"],
        MYSQL_REPLICA_PASSWORD="replica-secret",  # noqa: S106 - 테스트 픽스처 값
    )
    summary = settings.describe_routing()

    assert summary["mode"] == "router-replicated"
    assert summary["sticky_after_write"] is True
    assert "super-secret" not in summary["writer"]
    assert "***" in summary["writer"]
    assert all("replica-secret" not in url for url in summary["readers"])
    assert all("***" in url for url in summary["readers"])

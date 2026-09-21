"""read-only 세션의 쓰기 차단은 `DB_ROUTER_ENABLED` 와 무관하다.

예전에는 차단이 `RoutingSession.get_bind()` 안에만 있었다. `RoutingSession` 은
`DB_ROUTER_ENABLED=true` 일 때만 만들어지므로, **기본값(false)에서는** `mark_read_only()`
를 불러도 ORM flush·Core DML·Raw `text()` DML 이 전부 통과했다. read-only 는 replica
라우팅의 부산물이 아니라 Dependency 계약이라, 집행 지점을 `Session` 이벤트로 옮겼다.

판별은 default-deny 다. 괄호 깊이 0 의 단어만 훑어 최상위 구문이 읽기임이 확실할 때만
통과시킨다 — 읽기 전용 CTE(`WITH ... SELECT`)는 허용하고, 최상위에 쓰기 키워드가 있거나
잠금을 잡거나 multi-statement 이거나 따옴표·괄호가 무너진 문장은 거부한다.

테스트 모델은 별도 `DeclarativeBase` 를 쓴다 — 공유 metadata 와 migration 을 오염시키지
않기 위해서다.
"""

import pytest
import pytest_asyncio
from sqlalchemy import Integer, String, delete, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    _text_is_readable,  # noqa: PLC2701
    assert_writable,
    create_routing_sessionmaker,
    is_read_only,
    mark_read_only,
)


class _TestBase(DeclarativeBase):
    """테스트 전용 metadata — 앱 Base 와 분리한다."""


class Widget(_TestBase):
    __tablename__ = "guard_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest_asyncio.fixture(params=["router_off", "router_on"])
async def maker(request):
    """라우터 on/off 두 구성을 같은 계약으로 검증한다.

    `router_off` 는 `DB_ROUTER_ENABLED=false`(기본값)의 세션 팩토리와 같은 모양이다.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    if request.param == "router_on":
        router = DatabaseRouter(writer=engine, readers=[], sticky_after_write=True)
        factory = create_routing_sessionmaker(router)
    else:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with factory() as seed:
        await seed.execute(insert(Widget).values(id=1, name="seed"))
        await seed.commit()

    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def read_only(maker):
    async with maker() as session:
        mark_read_only(session)
        yield session


@pytest_asyncio.fixture
async def writable(maker):
    async with maker() as session:
        yield session


async def _rows(factory) -> int:
    async with factory() as session:
        return len((await session.execute(select(Widget))).scalars().all())


# ---------------------------------------------------------------- 중앙 API


async def test_is_read_only_reports_marking(maker):
    async with maker() as session:
        assert is_read_only(session) is False
        mark_read_only(session)
        assert is_read_only(session) is True


async def test_assert_writable_raises_only_when_marked(maker):
    async with maker() as session:
        assert_writable(session)  # 표시 전에는 통과
        mark_read_only(session)
        with pytest.raises(ReadOnlyRoutingError):
            assert_writable(session)


# ---------------------------------------------------------------- 쓰기 차단


async def test_orm_flush_is_blocked(read_only, maker):
    read_only.add(Widget(name="orm"))

    with pytest.raises(ReadOnlyRoutingError):
        await read_only.flush()

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize("statement_name", ["insert", "update", "delete"])
async def test_core_dml_is_blocked(read_only, maker, statement_name):
    statement = {
        "insert": insert(Widget).values(name="core"),
        "update": update(Widget).values(name="changed"),
        "delete": delete(Widget),
    }[statement_name]

    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(statement)

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO guard_widgets (name) VALUES ('raw')",
        "UPDATE guard_widgets SET name = 'raw'",
        "DELETE FROM guard_widgets",
        "  insert into guard_widgets (name) values ('lower')",
        "/* comment */ UPDATE guard_widgets SET name = 'x'",
        "DROP TABLE guard_widgets",
        "CREATE TABLE t2 (id INT)",
    ],
)
async def test_raw_dml_and_ddl_are_blocked(read_only, maker, sql):
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text(sql))

    await read_only.rollback()
    assert await _rows(maker) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM guard_widgets FOR UPDATE",
        "SELECT * FROM guard_widgets LOCK IN SHARE MODE",
        "SELECT 1; DELETE FROM guard_widgets",
        "CALL some_procedure()",
        "지원하지 않는 문장",
    ],
)
async def test_unknown_or_locking_statements_are_denied_by_default(read_only, sql):
    """default-deny — 확실히 읽기라고 판단되지 않으면 거부한다."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text(sql))


# ---------------------------------------------------------------- 읽기 허용


async def test_orm_select_is_allowed(read_only):
    rows = (await read_only.execute(select(Widget))).scalars().all()

    assert [row.name for row in rows] == ["seed"]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM guard_widgets",
        "  select id from guard_widgets  ",
        "SELECT 1;",
        "/* 주석 */ SELECT name FROM guard_widgets",
    ],
)
async def test_raw_select_is_allowed(read_only, sql):
    await read_only.execute(text(sql))


# ---------------------------------------------------------------- 대조군


async def test_writable_session_can_write(writable, maker):
    await writable.execute(insert(Widget).values(name="ok"))
    await writable.commit()

    assert await _rows(maker) == 2


async def test_writable_session_raw_dml_succeeds(writable, maker):
    await writable.execute(text("INSERT INTO guard_widgets (name) VALUES ('raw-ok')"))
    await writable.commit()

    assert await _rows(maker) == 2


# ------------------------------------------------- 깊이 0 스캔 (적대적 케이스)

_READABLE = [
    "SELECT id FROM item",
    "select id from item",
    "WITH r AS (SELECT id FROM item) SELECT id FROM r",
    "with r as (select id from item) select id from r",
    "WITH a AS (SELECT 1), b AS (SELECT 2) SELECT * FROM a JOIN b",
    "WITH RECURSIVE t(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM t WHERE n<5) SELECT * FROM t",
    "SELECT * FROM t WHERE note = 'please DELETE this row'",
    "SELECT * FROM t WHERE note = 'it''s an UPDATE'",
    "SELECT `update` FROM t",
    "SELECT (SELECT max(id) FROM other) AS m FROM t",
    "/* comment */ SELECT 1",
]

_UNREADABLE = [
    "WITH r AS (SELECT id FROM item) UPDATE item SET name='x'",
    "with r as (select id from item) update item set name='x'",
    "WITH r AS (SELECT id FROM item) DELETE FROM item",
    "UPDATE item SET name='x'",
    "INSERT INTO item VALUES (1)",
    "DROP TABLE item",
    "SELECT id FROM item FOR UPDATE",
    "SELECT id FROM item LOCK IN SHARE MODE",
    "SELECT 1; DROP TABLE item",
    "LOAD DATA INFILE 'x' INTO TABLE item",
    "SELECT * FROM t WHERE x = 'unclosed",
    "SELECT * FROM (SELECT 1",
    "",
]


@pytest.mark.parametrize("sql", _READABLE)
def test_depth0_scan_accepts_reads(sql):
    """최상위 구문이 SELECT/WITH...SELECT 면 통과한다 — 문자열·역따옴표 안은 보지 않는다."""
    assert _text_is_readable(sql) is True


@pytest.mark.parametrize("sql", _UNREADABLE)
def test_depth0_scan_rejects_writes_and_broken_input(sql):
    """깊이 0 에 쓰기 키워드가 있거나 스캔이 무너지면 거부한다(fail-closed)."""
    assert _text_is_readable(sql) is False


# ------------------------------------------------- CTE 조회 (Raw / ORM 대칭)


async def test_raw_cte_select_is_allowed(read_only):
    """Raw CTE 조회가 읽기 전용 세션에서 실행된다."""
    rows = await read_only.execute(
        text("WITH r AS (SELECT name FROM guard_widgets) SELECT name FROM r")
    )

    assert [row[0] for row in rows] == ["seed"]


async def test_orm_cte_select_stays_allowed(read_only):
    """ORM 이 만든 CTE 조회는 예전처럼 통과한다(회귀 방지)."""
    cte = select(Widget.name).cte("r")
    rows = await read_only.execute(select(cte.c.name))

    assert [row[0] for row in rows] == ["seed"]

"""Raw SQL Base 계층 계약 — RAW-REP-001~007, AR-003, NFR-001/004, TEST-001.

in-memory SQLite 로 실제 SQL 을 돌린다. Raw 계층의 계약은 "결과 형태가 무엇이고,
파라미터가 정말 바인딩되는가"이므로 mock 으로는 검증되지 않는다.

가장 중요한 두 가지:
    · **named bind parameter** — 값이 SQL 문자열에 보간되면 안 된다(RAW-REP-003).
    · **ORM Base 와 상속 관계 없음** — 하나의 Base 가 ORM 객체와 Raw row 를 동시에
      반환하면 호출자가 무엇을 받는지 시그니처로 알 수 없다(AR-003).
"""

from __future__ import annotations

import logging

import pytest
import pytest_asyncio
from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.exception import DatabaseException
from app.core.repositories.raw_crud_base import RawCRUDBase
from app.core.repositories.raw_repository_base import RawRepositoryBase

CREATE_TABLE = text(
    """
    CREATE TABLE raw_orders (
        id INTEGER PRIMARY KEY,
        customer TEXT NOT NULL,
        amount NUMERIC NOT NULL
    )
    """
)

SEED = text("INSERT INTO raw_orders (id, customer, amount) VALUES (:id, :customer, :amount)")


class OrderRawRepository(RawRepositoryBase):
    """기능 Repository 대역 — 도메인 SQL 은 Base 가 아니라 여기가 소유한다."""

    async def by_customer(self, *, customer: str) -> list[RowMapping]:
        statement = text("SELECT * FROM raw_orders WHERE customer = :customer ORDER BY id")
        rows = await self.fetch_all(
            statement,
            {"customer": customer},
            query_name="order.by_customer",
        )
        return list(rows)

    async def total_amount(self) -> object:
        return await self.fetch_scalar(
            text("SELECT COALESCE(SUM(amount), 0) FROM raw_orders"),
            query_name="order.total_amount",
        )

    async def raise_amount(self, *, customer: str, delta: int) -> int:
        return await self.execute(
            text("UPDATE raw_orders SET amount = amount + :delta WHERE customer = :customer"),
            {"customer": customer, "delta": delta},
            query_name="order.raise_amount",
        )


@pytest_asyncio.fixture
async def repository():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db_session:
        await db_session.execute(CREATE_TABLE)
        for index, (customer, amount) in enumerate(
            [("alice", 100), ("bob", 200), ("alice", 50)], start=1
        ):
            await db_session.execute(SEED, {"id": index, "customer": customer, "amount": amount})
        await db_session.commit()
        yield OrderRawRepository(db_session)

    await engine.dispose()


# =============================================================================
# AR-003 — ORM Base 와 독립된 계층
# =============================================================================
def test_raw_base_does_not_inherit_orm_base():
    """하나의 Base 가 ORM 모델과 Raw row 를 동시에 반환하면 안 된다."""
    from app.core.repositories.crud_base import CRUDBase
    from app.core.repositories.repository_base import BaseRepository

    assert not issubclass(RawRepositoryBase, BaseRepository)
    assert not issubclass(RawRepositoryBase, CRUDBase)
    assert not issubclass(RawCRUDBase, CRUDBase)
    assert issubclass(RawRepositoryBase, RawCRUDBase), "Raw 계층은 자체 primitive 를 상속한다"


def test_raw_base_has_no_transaction_control():
    """commit/rollback 은 Raw Base 의 책임도 아니다 (RAW-REP-001/007)."""
    for base in (RawCRUDBase, RawRepositoryBase):
        for forbidden in ("commit", "rollback"):
            assert not hasattr(base, forbidden), f"{base.__name__} 에 {forbidden} 이 있다"


def test_raw_base_offers_no_arbitrary_sql_entry_point():
    """``execute(sql: str)`` 같은 만능 메서드를 제공하지 않는다 (RAW-REP-001).

    문자열을 그대로 받는 진입점이 하나라도 있으면 f-string 보간이 그리로 몰린다.
    """
    import inspect

    signature = inspect.signature(RawRepositoryBase.execute)
    annotation = signature.parameters["statement"].annotation
    assert "TextClause" in str(annotation), f"statement 가 TextClause 계약이 아니다: {annotation}"


# =============================================================================
# RAW-REP-001/005 — 결과 형태
# =============================================================================
async def test_fetch_all_returns_row_mappings(repository):
    rows = await repository.by_customer(customer="alice")

    assert len(rows) == 2
    assert isinstance(rows[0], RowMapping), "RowMapping 이 아니면 Service 가 dict 변환을 못 한다"
    assert rows[0]["customer"] == "alice"
    assert [row["id"] for row in rows] == [1, 3]


async def test_fetch_one_returns_single_mapping_or_none(repository):
    statement = text("SELECT * FROM raw_orders WHERE id = :id")

    found = await repository.fetch_one(statement, {"id": 2}, query_name="order.by_id")
    assert found is not None
    assert found["customer"] == "bob"

    missing = await repository.fetch_one(statement, {"id": 999}, query_name="order.by_id")
    assert missing is None


async def test_fetch_all_on_empty_result_returns_empty_sequence(repository):
    rows = await repository.by_customer(customer="없는사람")
    assert rows == []


async def test_fetch_scalar_returns_plain_value(repository):
    total = await repository.total_amount()
    assert int(total) == 350


async def test_execute_returns_affected_row_count(repository):
    affected = await repository.raise_amount(customer="alice", delta=10)
    assert affected == 2

    rows = await repository.by_customer(customer="alice")
    assert [int(row["amount"]) for row in rows] == [110, 60]


async def test_execute_does_not_commit(repository):
    """Raw DML 도 커밋하지 않는다 — 트랜잭션 경계는 쓰기 View 의 몫이다 (RAW-REP-007)."""
    committed: list[str] = []
    original_commit = repository.db_session.commit

    async def _tracking_commit(*args, **kwargs):
        committed.append("commit")
        return await original_commit(*args, **kwargs)

    repository.db_session.commit = _tracking_commit  # type: ignore[method-assign]
    await repository.raise_amount(customer="bob", delta=1)

    assert committed == [], "Raw Repository 가 커밋했다 (RAW-REP-007 위반)"


# =============================================================================
# RAW-REP-003 — named parameter 가 실제로 바인딩되는가
# =============================================================================
async def test_parameters_are_bound_not_interpolated(repository):
    """injection 대표 입력이 데이터로만 취급돼야 한다."""
    malicious = "alice'; DROP TABLE raw_orders; --"

    rows = await repository.by_customer(customer=malicious)

    assert rows == [], "주입 문자열이 값으로 매칭되지 않아야 한다"
    # 테이블이 살아 있어야 한다 — 드롭됐다면 다음 조회에서 터진다.
    assert len(await repository.by_customer(customer="alice")) == 2


async def test_bound_parameters_do_not_appear_in_compiled_sql(repository):
    """컴파일된 SQL 본문에 값이 박혀 있으면 바인딩이 아니다."""
    statement = text("SELECT * FROM raw_orders WHERE customer = :customer")
    compiled = str(statement.compile())

    assert ":customer" in compiled
    assert "alice" not in compiled


# =============================================================================
# RAW-REP-002 / NFR-004 — query_name 로깅, 민감정보 미노출
# =============================================================================
async def test_public_api_requires_keyword_only_query_name():
    """query_name 은 keyword-only 여야 위치 인자와 섞여 조용히 어긋나지 않는다."""
    import inspect

    for name in ("fetch_one", "fetch_all", "fetch_scalar", "execute"):
        parameter = inspect.signature(getattr(RawRepositoryBase, name)).parameters["query_name"]
        assert (
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
        ), f"{name} 의 query_name 이 keyword-only 가 아니다"


def _our_log_messages(caplog) -> str:
    """이 Base 가 직접 남긴 로그만 모은다.

    서드파티 드라이버 로거(aiosqlite·sqlalchemy.engine)는 DEBUG 에서 SQL 과
    파라미터를 그대로 찍는다. 그건 별도 관심사이므로
    ``tests/core/test_sql_logging_leak.py`` 에서 따로 다룬다.
    """
    return " ".join(
        record.getMessage() for record in caplog.records if record.name == "raw_repository"
    )


async def test_logs_query_name_and_duration_without_sql_or_params(repository, caplog):
    """로그에 쿼리 이름과 소요 시간은 남기되 SQL 본문·파라미터는 남기지 않는다."""
    with caplog.at_level(logging.DEBUG, logger="raw_repository"):
        await repository.by_customer(customer="alice")

    messages = _our_log_messages(caplog)

    assert "order.by_customer" in messages, "query_name 이 로그에 없다"
    assert "ms" in messages, "소요 시간이 로그에 없다"
    assert "SELECT" not in messages.upper(), f"SQL 본문이 로그에 남았다: {messages}"
    assert "alice" not in messages, f"바인딩 파라미터가 로그에 남았다: {messages}"


async def test_failure_log_also_hides_sql_and_params(repository, caplog):
    statement = text("SELECT * FROM 없는테이블 WHERE customer = :customer")

    with caplog.at_level(logging.DEBUG, logger="raw_repository"):
        with pytest.raises(DatabaseException):
            await repository.fetch_all(
                statement,
                {"customer": "top-secret"},
                query_name="order.broken",
            )

    messages = _our_log_messages(caplog)
    assert "order.broken" in messages
    assert "top-secret" not in messages, f"실패 로그에 파라미터가 남았다: {messages}"
    assert "없는테이블" not in messages, f"실패 로그에 SQL 본문이 남았다: {messages}"


# =============================================================================
# RAW-REP-002 — 예외 변환
# =============================================================================
async def test_sqlalchemy_errors_become_database_exception(repository):
    with pytest.raises(DatabaseException) as exc_info:
        await repository.fetch_all(
            text("SELECT * FROM 없는테이블"),
            query_name="order.missing_table",
        )

    assert exc_info.value.__cause__ is not None, "원본 예외가 chaining 으로 보존돼야 한다"


async def test_error_detail_does_not_leak_parameters(repository):
    with pytest.raises(DatabaseException) as exc_info:
        await repository.fetch_one(
            text("SELECT * FROM 없는테이블 WHERE customer = :customer"),
            {"customer": "top-secret"},
            query_name="order.broken",
        )

    rendered = str(exc_info.value.detail)
    assert "top-secret" not in rendered, f"detail 로 파라미터가 유출됐다: {rendered}"
    assert "order.broken" in rendered, "어떤 쿼리인지는 알 수 있어야 한다"


# =============================================================================
# RAW-REP-004 — 식별자 allowlist
# =============================================================================
def test_identifier_allowlist_rejects_unknown_keys():
    """정렬 키처럼 바인딩할 수 없는 식별자는 코드가 소유한 allowlist 에서만 고른다."""
    from app.core.repositories.raw_repository_base import resolve_identifier

    allowed = {"date": "o.created_at", "amount": "o.total_amount"}

    assert resolve_identifier("amount", allowed) == "o.total_amount"

    with pytest.raises(ValueError, match="허용되지 않은"):
        resolve_identifier("o.created_at; DROP TABLE x", allowed)
    with pytest.raises(ValueError):
        resolve_identifier("unknown", allowed)


def test_sort_direction_allowlist():
    from app.core.repositories.raw_repository_base import resolve_sort_direction

    assert resolve_sort_direction("asc") == "ASC"
    assert resolve_sort_direction("DESC") == "DESC"

    with pytest.raises(ValueError):
        resolve_sort_direction("asc; DROP TABLE x")

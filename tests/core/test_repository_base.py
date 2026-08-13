"""ORM Repository Base 계약 — ORM-REP-001~006, ORM-MDL-003, TEST-001.

in-memory SQLite 로 실제 CRUD 를 돌린다. Base 의 계약은 "SQL 이 정말 그렇게 나가는가"
이므로 mock 으로는 검증되지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, String, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.exception import DatabaseException, DuplicateException, NotFoundException
from app.core.models.models_base import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin
from app.core.repositories.repository_base import BaseRepository


class _TestBase(DeclarativeBase):
    """테스트 전용 Declarative Base.

    공유 ``Base`` 에 테스트 모델을 붙이면 ``Base.metadata`` 가 오염되어
    스키마 스냅샷·마이그레이션 정합성 테스트가 유령 테이블을 본다.
    Mixin 은 그대로 재사용하므로 공통 필드 정책도 함께 검증된다.
    """

    type_annotation_map = {datetime: DateTime(timezone=True)}


class Widget(_TestBase, UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin):
    __tablename__ = "repo_base_widgets"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class WidgetRepository(BaseRepository[Widget]):  # type: ignore[type-var]
    model = Widget


@pytest_asyncio.fixture
async def repository():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 는 기본적으로 FK/UNIQUE 위반을 즉시 올리지만, 명시적으로 켜 둔다.
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(_TestBase.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield WidgetRepository(db_session)

    await engine.dispose()


# =============================================================================
# ORM-REP-003 — 입력 불변성
# =============================================================================
async def test_create_does_not_mutate_caller_dict(repository):
    """Repository 가 호출자의 dict 를 건드리면 안 된다.

    예전 구현은 ``data["id"] = str(uuid4())`` 로 호출자 데이터를 직접 바꿨다.
    Service 가 같은 dict 를 다른 용도로 재사용하면 조용히 오염된다.
    """
    payload: dict[str, Any] = {"name": "gadget"}
    snapshot = dict(payload)

    created = await repository.create(payload)

    assert payload == snapshot, f"입력 dict 가 변경됐다: {payload}"
    assert created.id, "모델 default 로 id 가 채워져야 한다"


async def test_create_respects_explicit_id(repository):
    """호출자가 id 를 주면 그대로 쓴다."""
    created = await repository.create({"id": "fixed-id-001", "name": "explicit"})
    assert created.id == "fixed-id-001"


# =============================================================================
# ORM-REP-002 — 최소 공개 CRUD
# =============================================================================
async def test_get_by_id_and_or_raise(repository):
    created = await repository.create({"name": "alpha"})

    assert (await repository.get_by_id(created.id)) is not None
    assert (await repository.get_by_id("없는-id")) is None

    fetched = await repository.get_by_id_or_raise(created.id)
    assert fetched.id == created.id

    with pytest.raises(NotFoundException):
        await repository.get_by_id_or_raise("없는-id")


async def test_list_paginates(repository):
    for index in range(5):
        await repository.create({"name": f"item-{index}"})

    first_page = await repository.list(skip=0, limit=2)
    second_page = await repository.list(skip=2, limit=2)

    assert len(first_page) == 2
    assert len(second_page) == 2
    assert {w.id for w in first_page}.isdisjoint({w.id for w in second_page})


async def test_count_with_and_without_filters(repository):
    await repository.create({"name": "red-1", "color": "red"})
    await repository.create({"name": "red-2", "color": "red"})
    await repository.create({"name": "blue-1", "color": "blue"})

    assert await repository.count() == 3
    assert await repository.count(color="red") == 2


async def test_update_by_id_returns_none_when_missing(repository):
    created = await repository.create({"name": "before"})

    updated = await repository.update_by_id(created.id, {"name": "after"})
    assert updated is not None
    assert updated.name == "after"

    assert await repository.update_by_id("없는-id", {"name": "x"}) is None


async def test_delete_by_id_reports_whether_a_row_was_removed(repository):
    created = await repository.create({"name": "doomed"})

    assert await repository.delete_by_id(created.id) is True
    assert await repository.delete_by_id(created.id) is False


# =============================================================================
# ORM-REP-004 — 존재 확인은 EXISTS
# =============================================================================
async def test_exists_uses_sql_exists_not_count(repository):
    """``EXISTS`` 는 첫 행에서 멈춘다. ``COUNT(*)`` 는 전부 센다."""
    created = await repository.create({"name": "here"})

    statements: list[str] = []

    @event.listens_for(repository.db_session.sync_session, "do_orm_execute")
    def _capture(orm_execute_state):
        statements.append(str(orm_execute_state.statement).upper())

    assert await repository.exists(created.id) is True
    assert await repository.exists("없는-id") is False

    assert statements, "쿼리를 관측하지 못했다"
    assert any(
        "EXISTS" in sql for sql in statements
    ), f"존재 확인이 EXISTS 를 쓰지 않는다: {statements}"
    assert not any(
        "COUNT" in sql for sql in statements
    ), f"존재 확인에 COUNT 가 남아 있다: {statements}"


async def test_exists_returns_bool(repository):
    created = await repository.create({"name": "boolcheck"})
    result = await repository.exists(created.id)
    assert result is True and isinstance(result, bool)


# =============================================================================
# ORM-REP-006 — 예외 변환 일관성
# =============================================================================
async def test_create_translates_duplicate(repository):
    await repository.create({"name": "unique-name"})
    with pytest.raises(DuplicateException):
        await repository.create({"name": "unique-name"})


async def test_update_translates_duplicate(repository):
    first = await repository.create({"name": "one"})
    await repository.create({"name": "two"})

    with pytest.raises(DuplicateException):
        await repository.update_by_id(first.id, {"name": "two"})


@pytest.mark.parametrize(
    "operation",
    ["create", "update_by_id", "delete_by_id", "list", "count", "exists"],
)
async def test_unexpected_db_errors_become_database_exception(repository, monkeypatch, operation):
    """모든 공개 경로가 같은 정책으로 SQLAlchemy 오류를 변환해야 한다.

    예전에는 create/update/delete 만 변환하고 나머지는 드라이버 예외를 그대로
    흘려보냈다. 호출자가 계층마다 다른 예외를 처리해야 했다.
    """
    from sqlalchemy.exc import OperationalError

    async def boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("연결 끊김"))

    monkeypatch.setattr(repository.db_session, "execute", boom)
    monkeypatch.setattr(repository.db_session, "flush", boom)
    monkeypatch.setattr(repository.db_session, "get", boom)

    arguments: dict[str, tuple] = {
        "create": ({"name": "x"},),
        "update_by_id": ("some-id", {"name": "y"}),
        "delete_by_id": ("some-id",),
        "list": (),
        "count": (),
        "exists": ("some-id",),
    }

    with pytest.raises(DatabaseException):
        await getattr(repository, operation)(*arguments[operation])


async def test_error_detail_does_not_leak_sql_parameters(repository):
    """사용자에게 가는 detail 에 바인딩 파라미터가 실려서는 안 된다 (NFR-001)."""
    await repository.create({"name": "secret-value"})

    with pytest.raises(DuplicateException) as exc_info:
        await repository.create({"name": "secret-value"})

    rendered = str(exc_info.value.detail)
    assert "secret-value" not in rendered, f"입력값이 오류 detail 로 새어나갔다: {rendered}"


# =============================================================================
# ORM-MDL-003 — PK 타입 계약
# =============================================================================
def test_repository_declares_primary_key_type():
    """``BaseRepository[ModelT, PrimaryKeyT]`` 가 정식 계약이어야 한다."""
    import typing

    parameters = getattr(BaseRepository, "__type_params__", None) or typing.get_args(
        BaseRepository.__orig_bases__[-1]  # type: ignore[attr-defined]
    )
    assert len(parameters) >= 2, f"PK 타입 파라미터가 없다: {parameters}"


def test_single_parameter_form_still_works():
    """기존 ``BaseRepository[Model]`` 선언이 그대로 유효해야 한다 (기본값 str)."""

    class _Probe(BaseRepository[Widget]):  # type: ignore[type-var]
        model = Widget

    assert _Probe.model is Widget


# =============================================================================
# ORM-REP-001 — CRUDBase 는 primitive 만
# =============================================================================
def test_crud_base_has_no_transaction_control():
    """commit/rollback 은 Base 의 책임이 아니다 (TX-004)."""
    from app.core.repositories.crud_base import CRUDBase

    for forbidden in ("commit", "rollback"):
        assert not hasattr(CRUDBase, forbidden), f"CRUDBase 에 {forbidden} 이 있다"

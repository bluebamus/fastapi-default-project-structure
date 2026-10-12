"""DB 오류 변환 표 — service-hardening ADR-008 ②·ADR-022 (F-011·F-025).

예전에는 ORM 이 모든 ``IntegrityError`` 를 409 DUPLICATE 로 보냈고(NOT NULL·FK 위반의 원인이
가려졌다), 기능 Repository 의 추가 쿼리는 변환을 거치지 않았으며, 실패 로그에 드라이버
메시지(SQL·바인딩 값)가 그대로 실렸다.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import ForeignKey, String, event, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.exception import (
    ConflictException,
    DatabaseException,
    DuplicateException,
    ValidationException,
)
from app.core.repositories import repository_base as repository_module
from app.core.repositories.db_errors import DatabaseErrorTranslator
from app.core.repositories.raw_repository_base import RawRepositoryBase
from app.core.repositories.repository_base import BaseRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRET = "secret-value-7f3a"


class _MySQLError(Exception):
    """pymysql 예외의 모양 — ``args = (code, message)``."""


def _mysql(error_class, code: int):
    orig = _MySQLError(code, f"(code {code}) value '{SECRET}' in INSERT INTO t")
    return error_class("INSERT INTO t VALUES (%s)", (SECRET,), orig)


# =============================================================================
# 변환 표 (드라이버 코드)
# =============================================================================
@pytest.mark.parametrize(
    ("error", "expected", "status"),
    [
        (_mysql(IntegrityError, 1062), DuplicateException, 409),
        (_mysql(IntegrityError, 1048), ValidationException, 422),
        # pymysql 은 1364 를 OperationalError 로 올린다 — 클래스가 아니라 코드로 판정한다.
        (_mysql(OperationalError, 1364), ValidationException, 422),
        (_mysql(IntegrityError, 1452), ValidationException, 422),
        (_mysql(IntegrityError, 1451), ConflictException, 409),
        (_mysql(IntegrityError, 3819), DatabaseException, 500),  # CHECK 위반 등 그 밖
        (_mysql(OperationalError, 2013), DatabaseException, 500),  # 연결 끊김
    ],
    ids=["1062", "1048", "1364", "1452", "1451", "other-integrity", "connection"],
)
def test_mysql_codes_map_to_their_status(error, expected, status):
    translated = DatabaseErrorTranslator.translate(error, detail={"model": "T"})

    assert type(translated) is expected
    assert translated.status_code == status


def test_referenced_row_is_conflict_not_duplicate():
    """1451(참조 중)은 409 지만 DUPLICATE 가 아니다 — 클라이언트 분기가 다르다."""
    translated = DatabaseErrorTranslator.translate(_mysql(IntegrityError, 1451), detail={})
    assert translated.error_code == "CONFLICT"


def test_translated_exception_carries_no_driver_text():
    translated = DatabaseErrorTranslator.translate(_mysql(IntegrityError, 1062), detail={"a": 1})
    rendered = f"{translated.message} {translated.detail}"
    assert SECRET not in rendered
    assert "INSERT" not in rendered


def test_describe_is_type_and_code_only():
    assert DatabaseErrorTranslator.describe(_mysql(IntegrityError, 1062)) == (
        "IntegrityError(code=1062)"
    )
    assert DatabaseErrorTranslator.describe(OperationalError("x", {}, Exception("y"))) == (
        "OperationalError"
    )


# =============================================================================
# SQLite 메시지 대체 경로 — 실제 드라이버 오류로 확인
# =============================================================================
class _Base(DeclarativeBase):
    pass


class Parent(_Base):
    __tablename__ = "db_errors_parents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class Child(_Base):
    __tablename__ = "db_errors_children"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(ForeignKey("db_errors_parents.id"), nullable=False)


class ParentRepository(BaseRepository[Parent]):  # type: ignore[type-var]
    model = Parent


class ChildRepository(BaseRepository[Child]):  # type: ignore[type-var]
    model = Child


class ParentRawRepository(RawRepositoryBase):
    async def insert(self, *, pk: str, name: str) -> int:
        return await self.execute(
            text("INSERT INTO db_errors_parents (id, name) VALUES (:id, :name)"),
            {"id": pk, "name": name},
            query_name="parent.insert",
        )


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        hide_parameters=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(_Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def test_sqlite_unique_is_duplicate(db_session):
    repository = ParentRepository(db_session)
    await repository.create({"id": "p1", "name": SECRET})
    with pytest.raises(DuplicateException):
        await repository.create({"id": "p2", "name": SECRET})


async def test_sqlite_not_null_is_422_not_duplicate(db_session):
    """예전에는 NOT NULL 위반도 409 DUPLICATE 였다."""
    with pytest.raises(ValidationException) as exc_info:
        await ParentRepository(db_session).create({"id": "p1", "name": None})
    assert exc_info.value.status_code == 422


async def test_sqlite_missing_reference_is_422(db_session):
    with pytest.raises(ValidationException):
        await ChildRepository(db_session).create({"id": "c1", "parent_id": "없는-부모"})


async def test_raw_duplicate_uses_the_same_table(db_session):
    """Raw 계층도 같은 표를 쓴다 — 예전에는 무엇이든 500 이었다."""
    repository = ParentRawRepository(db_session)
    await repository.insert(pk="p1", name="dup")
    with pytest.raises(DuplicateException):
        await repository.insert(pk="p2", name="dup")


# =============================================================================
# 기능 Repository 의 추가 쿼리도 변환을 거친다
# =============================================================================
async def test_feature_query_errors_are_translated(db_session, monkeypatch):
    """``list_active`` 처럼 Base 밖의 쿼리가 드라이버 예외를 그대로 흘렸다."""
    from app.features.catalog.repositories.product_repository import ProductRepository

    async def boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("연결 끊김"))

    monkeypatch.setattr(db_session, "execute", boom)
    repository = ProductRepository(db_session)

    with pytest.raises(DatabaseException):
        await repository.list_active()
    with pytest.raises(DatabaseException):
        await repository.count_active()


def test_feature_repositories_do_not_execute_directly():
    """기능 Repository 는 ``self.db_session.execute`` 대신 ``self._execute`` 를 쓴다."""
    offenders = []
    for path in sorted((PROJECT_ROOT / "app" / "features").glob("*/repositories/*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"self\.db_session\.execute\(", line):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{lineno}")
    assert not offenders, f"변환을 거치지 않는 쿼리: {offenders}"


# =============================================================================
# 로그 — 타입과 코드만 (R-07)
# =============================================================================
async def test_failure_log_has_no_sql_or_parameters(db_session, caplog):
    repository = ParentRepository(db_session)
    await repository.create({"id": "p1", "name": SECRET})

    with caplog.at_level(logging.INFO, logger=repository_module.logger.name):
        with pytest.raises(DuplicateException):
            await repository.create({"id": "p2", "name": SECRET})

    records = [r for r in caplog.records if r.name == repository_module.logger.name]
    assert records, "실패 로그가 없다"
    message = " ".join(r.getMessage() for r in records)
    assert SECRET not in message, f"바인딩 값이 로그에 실렸다: {message}"
    assert "INSERT" not in message.upper(), f"SQL 이 로그에 실렸다: {message}"
    assert "IntegrityError" in message
    # 클라이언트 원인(409)은 WARNING — ERROR 경보를 흐리지 않는다.
    assert all(r.levelno == logging.WARNING for r in records)


async def test_server_side_failure_logs_at_error(db_session, monkeypatch, caplog):
    async def boom(*args, **kwargs):
        raise _mysql(OperationalError, 2013)

    monkeypatch.setattr(db_session, "execute", boom)
    with caplog.at_level(logging.INFO, logger=repository_module.logger.name):
        with pytest.raises(DatabaseException):
            await ParentRepository(db_session).count()

    records = [r for r in caplog.records if r.name == repository_module.logger.name]
    assert [r.levelno for r in records] == [logging.ERROR]
    assert SECRET not in records[0].getMessage()
    assert "code=2013" in records[0].getMessage()


def test_application_engines_hide_bound_parameters():
    """엔진이 예외 문자열에서 바인딩 값을 빼야 어디로 흘러도 비밀이 실리지 않는다."""
    from app.core.db import session as session_module

    engines = [
        session_module.engine,
        session_module.background_engine,
        session_module._create_read_engine(session_module.db_settings.MYSQL_WRITER_URL),
    ]
    for engine in engines:
        assert engine.sync_engine.hide_parameters is True

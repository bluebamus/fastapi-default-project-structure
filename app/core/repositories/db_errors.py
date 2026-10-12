"""DB 오류 → 프로젝트 예외 변환의 단일 출처 (service-hardening ADR-008 ②·ADR-022).

ORM(``BaseRepository``)과 Raw(``RawRepositoryBase``) 두 계층이 **같은 표**로 변환한다.
예전에는 ORM 이 모든 ``IntegrityError`` 를 409 DUPLICATE 로 보내 NOT NULL·외래 키 위반의
원인이 가려졌고, Raw 는 무엇이든 500 이었다.

판정은 드라이버 오류 코드로 한다(예외 클래스가 아니라). pymysql 은 1364 처럼 무결성
위반을 ``OperationalError`` 로 올리기도 해서 클래스로는 갈리지 않는다.

============  =====================  ===========================================
MySQL 코드     SQLite 메시지           결과
============  =====================  ===========================================
1062          UNIQUE                 409 ``DuplicateException``
1048 · 1364   NOT NULL               422 ``ValidationException`` (필수 값 누락)
1452          FOREIGN KEY            422 ``ValidationException`` (참조 대상 없음)
1451          —                      409 ``ConflictException`` (다른 행이 참조 중)
그 외          그 외                   500 ``DatabaseException``
============  =====================  ===========================================

SQLite 는 외래 키 위반을 방향 구분 없이 "FOREIGN KEY constraint failed" 하나로 알린다 —
그래서 422 로만 보낸다(1451 의 409 는 MySQL 에서만 구분된다).

**원문을 싣지 않는다.** 드라이버 메시지에는 위반한 값과 SQL 이 들어 있다. 응답 detail 은
호출자가 넘긴 식별 정보뿐이고, 로그에는 ``describe()`` 가 만드는 예외 타입과 코드만 남긴다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.exception import (
    AppException,
    ConflictException,
    DatabaseException,
    DuplicateException,
    ValidationException,
)

_DUPLICATE_CODES = frozenset({1062})
_NOT_NULL_CODES = frozenset({1048, 1364})
_MISSING_REFERENCE_CODES = frozenset({1452})
_REFERENCED_CODES = frozenset({1451})


class DatabaseErrorTranslator:
    """SQLAlchemy 오류를 HTTP 의미가 있는 프로젝트 예외로 바꾼다(상태 없음)."""

    @staticmethod
    def driver_code(error: SQLAlchemyError) -> int | None:
        """드라이버 오류 코드(MySQL 정수 코드). 없으면 None."""
        if not isinstance(error, DBAPIError):
            return None
        args = getattr(error.orig, "args", ())
        return args[0] if args and isinstance(args[0], int) else None

    @classmethod
    def describe(cls, error: SQLAlchemyError) -> str:
        """로그용 요약 — 예외 타입과 드라이버 코드만. SQL·바인딩 값은 없다."""
        code = cls.driver_code(error)
        name = type(error).__name__
        return name if code is None else f"{name}(code={code})"

    @classmethod
    def translate(cls, error: SQLAlchemyError, detail: dict[str, Any]) -> AppException:
        """오류에 맞는 프로젝트 예외를 만든다(던지지 않는다 — 호출자가 ``from error`` 로 던진다)."""
        code = cls.driver_code(error)
        message = _sqlite_message(error)

        if code in _DUPLICATE_CODES or "UNIQUE constraint failed" in message:
            return DuplicateException(
                message="요청한 데이터가 기존 데이터와 충돌합니다.", detail=detail
            )
        if code in _NOT_NULL_CODES or "NOT NULL constraint failed" in message:
            return ValidationException(message="필수 값이 비어 있습니다.", detail=detail)
        if code in _MISSING_REFERENCE_CODES or "FOREIGN KEY constraint failed" in message:
            return ValidationException(message="참조하는 데이터가 없습니다.", detail=detail)
        if code in _REFERENCED_CODES:
            return ConflictException(
                message="다른 데이터가 참조하고 있어 처리할 수 없습니다.", detail=detail
            )
        return DatabaseException(message="데이터베이스 처리 중 오류가 발생했습니다.", detail=detail)


def _sqlite_message(error: SQLAlchemyError) -> str:
    """SQLite 드라이버 메시지(판정용). 코드가 없는 드라이버의 대체 경로라 SQLite 일 때만 본다."""
    if not isinstance(error, DBAPIError):
        return ""
    orig = error.orig
    if type(orig).__module__.startswith("sqlite3"):
        return str(orig)
    return ""

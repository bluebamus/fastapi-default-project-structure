"""Raw SQL 실행 primitive (RAW-REP-001).

ORM Base 와 **상속 관계를 만들지 않는다**(AR-003). 하나의 Base 가 ORM 객체와 Raw
row 를 동시에 반환하면 호출자가 무엇을 받는지 시그니처로 알 수 없고, 두 계층의
예외·로딩 정책이 서로 새어 든다. 공유하는 것은 ``AsyncSession`` 과 공통 예외·로깅
정책뿐이다.

이 클래스의 책임은 **SQL 실행과 결과 형태 변환**뿐이다.

설계 제약:
    · 입력은 문자열이 아니라 미리 만든 ``TextClause`` 다. 문자열을 받는 진입점이
      하나라도 있으면 f-string 보간이 그리로 몰린다(RAW-REP-003).
    · 반환은 ORM 객체가 아니라 ``RowMapping``·scalar·affected row count 다.
    · ``execute(sql: str)`` 같은 만능 메서드를 제공하지 않는다.
    · 예외를 삼키지 않고 커밋하지 않는다 — 변환은 ``RawRepositoryBase``,
      커밋은 쓰기 View 본문의 몫이다(TX-004).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from sqlalchemy import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause


class RawCRUDBase:
    """``text()`` 기반 SQL 실행 primitive.

    Attributes:
        db_session: 비동기 데이터베이스 세션
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """
        Args:
            db_session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        self.db_session = db_session

    async def _fetch_one(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> RowMapping | None:
        """첫 행을 ``RowMapping`` 으로 돌려준다. 결과가 없으면 ``None``."""
        result = await self.db_session.execute(statement, params or {})
        row = result.mappings().first()
        return row

    async def _fetch_all(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> Sequence[RowMapping]:
        """모든 행을 ``RowMapping`` 목록으로 돌려준다(없으면 빈 목록)."""
        result = await self.db_session.execute(statement, params or {})
        return result.mappings().all()

    async def _fetch_scalar(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """첫 행 첫 컬럼 값을 돌려준다(집계 쿼리용)."""
        result = await self.db_session.execute(statement, params or {})
        return result.scalar()

    async def _execute(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
    ) -> int:
        """DML 을 실행하고 영향받은 행 수를 돌려준다.

        커밋하지 않는다. ``flush`` 도 하지 않는다 — Raw DML 은 이미 SQL 을 직접
        발행하므로 ORM 의 보류 변경을 내보낼 것이 없다.
        """
        result = cast("CursorResult[Any]", await self.db_session.execute(statement, params or {}))
        return result.rowcount

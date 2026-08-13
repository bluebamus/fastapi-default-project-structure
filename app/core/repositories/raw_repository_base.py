"""Raw SQL Repository 의 공통 정책 (RAW-REP-002).

``RawCRUDBase`` 의 primitive 위에 **안정적인 public API + 예외 변환 + 쿼리 이름
중심 로깅**을 얹는다. 도메인 SQL 은 여기 두지 않는다 — 기능 Repository 가 SQL 과
쿼리 이름을 소유하고, Base 에는 ``query_name`` 만 넘긴다.

    class SalesReportRawRepository(RawRepositoryBase):
        async def daily_sales(self, *, start_date, end_date):
            statement = text("SELECT ... WHERE created_at >= :start_date")
            return await self.fetch_all(
                statement,
                {"start_date": start_date, "end_date": end_date},
                query_name="sales_report.daily_sales",
            )

관측성 (NFR-004):
    로그에는 ``query_name`` 과 소요 시간, 성공/실패만 남긴다. **SQL 본문과
    파라미터는 남기지 않는다** — Raw SQL 의 파라미터에는 사용자 식별자·검색어 등
    민감한 값이 그대로 들어 있고, 로그는 보통 외부 collector 로 흘러간다.
    쿼리를 특정하려면 SQL 이 아니라 이름을 보면 된다. 그래서 ``query_name`` 은
    keyword-only 필수 인자다 — 위치 인자와 섞여 조용히 빠지지 않게.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.elements import TextClause

from app.core.exception import DatabaseException
from app.core.repositories.raw_crud_base import RawCRUDBase
from app.utils.logs import get_logger

logger = get_logger("raw_repository")

# 정렬 방향은 바인딩할 수 없는 식별자다. 코드가 소유한 값만 허용한다.
_SORT_DIRECTIONS = {"ASC", "DESC"}


def resolve_identifier(requested: str, allowed: Mapping[str, str]) -> str:
    """요청된 키를 **코드가 소유한** SQL 식별자로 바꾼다 (RAW-REP-004).

    테이블명·컬럼명·정렬 방향은 bind parameter 로 넘길 수 없다. 그렇다고 요청값을
    SQL 에 그대로 넣으면 injection 이 된다. 그래서 요청값은 **키로만** 쓰고 실제
    식별자는 allowlist 에서 꺼낸다 — f-string 에 들어가는 값이 외부 입력이 아니라
    코드 상수가 되도록.

    Args:
        requested: 클라이언트가 보낸 정렬 키 같은 값.
        allowed: 허용 키 → 실제 SQL 식별자 매핑.

    Raises:
        ValueError: allowlist 에 없는 키. 호출자가 422 로 변환한다.
    """
    try:
        return allowed[requested]
    except KeyError:
        raise ValueError(
            f"허용되지 않은 식별자입니다: {requested!r} (가능: {sorted(allowed)})"
        ) from None


def resolve_sort_direction(requested: str) -> str:
    """정렬 방향을 ASC/DESC 중 하나로 확정한다 (RAW-REP-004)."""
    direction = requested.strip().upper()
    if direction not in _SORT_DIRECTIONS:
        raise ValueError(f"허용되지 않은 정렬 방향입니다: {requested!r} (가능: ASC, DESC)")
    return direction


class RawRepositoryBase(RawCRUDBase):
    """Raw SQL 기능 Repository 의 공통 기반.

    ``BaseRepository`` 를 상속하지 않는다 — ORM 계층과 평행한 독립 계층이다(AR-003).
    """

    @contextmanager
    def _observed(self, query_name: str) -> Iterator[None]:
        """실행을 감싸 소요 시간을 남기고 SQLAlchemy 오류를 변환한다.

        detail 에는 쿼리 이름만 넣는다. 드라이버 오류 원문에는 SQL 과 값이 함께
        들어 있어 그대로 응답에 실으면 유출된다(NFR-001).
        """
        started = time.perf_counter()
        try:
            yield
        except SQLAlchemyError as error:
            elapsed = (time.perf_counter() - started) * 1000
            # 원문은 서버 로그에만 남긴다.
            logger.error(
                "[raw] %s 실패 (%.1fms): %s",
                query_name,
                elapsed,
                type(error).__name__,
            )
            raise DatabaseException(
                message="데이터베이스 처리 중 오류가 발생했습니다.",
                detail={"query": query_name},
            ) from error
        else:
            elapsed = (time.perf_counter() - started) * 1000
            logger.debug("[raw] %s 완료 (%.1fms)", query_name, elapsed)

    async def fetch_one(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> RowMapping | None:
        """첫 행을 ``RowMapping`` 으로 돌려준다(없으면 ``None``)."""
        with self._observed(query_name):
            return await self._fetch_one(statement, params)

    async def fetch_all(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> Sequence[RowMapping]:
        """모든 행을 ``RowMapping`` 목록으로 돌려준다(없으면 빈 목록)."""
        with self._observed(query_name):
            return await self._fetch_all(statement, params)

    async def fetch_scalar(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> Any:
        """집계 등 단일 값을 돌려준다."""
        with self._observed(query_name):
            return await self._fetch_scalar(statement, params)

    async def execute(
        self,
        statement: TextClause,
        params: Mapping[str, Any] | None = None,
        *,
        query_name: str,
    ) -> int:
        """DML 을 실행하고 영향받은 행 수를 돌려준다(커밋하지 않는다)."""
        with self._observed(query_name):
            return await self._execute(statement, params)

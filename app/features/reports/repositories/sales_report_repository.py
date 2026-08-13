"""SalesReport Raw Repository — 일별 매출 집계 SQL 을 소유한다.

Base(``RawRepositoryBase``)에는 도메인 SQL 을 두지 않는다. SQL 과 컬럼 alias,
그리고 안정적인 ``query_name`` 상수는 이 파일이 소유한다(RAW-REP-002).

기간 경계에 관하여:
    "종료일 포함" 은 비즈니스 규칙이라 Service 가 해석하고, 여기에는 이미 계산된
    **반열린 구간** ``[start_at, end_at)`` 이 들어온다. ``DATE_ADD(:end, INTERVAL 1 DAY)``
    같은 방언 함수를 SQL 에 넣지 않은 이유이기도 하다 — 규칙이 SQL 에 숨으면
    단위 테스트가 DB 방언에 묶인다(지침서 §4.4).
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import RowMapping, text

from app.core.repositories.raw_repository_base import RawRepositoryBase

# 쿼리 이름은 로그의 안정적인 식별자다. 변경하면 대시보드·알람이 끊긴다.
QUERY_DAILY_SALES = "sales_report.daily_sales"

# 일별 집계. 값은 전부 named bind parameter 로 들어간다(RAW-REP-003).
# 표준 SQL 만 사용하므로 MySQL·SQLite 양쪽에서 동작한다 — 그래도 MySQL 실제 동작은
# 통합 테스트(@pytest.mark.mysql)가 확인한다(RAW-REP-006).
_DAILY_SALES_SQL = text(
    """
    SELECT
        DATE(o.created_at) AS sales_date,
        COUNT(*)           AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at <  :end_at
    GROUP BY DATE(o.created_at)
    ORDER BY sales_date ASC
    """
)


class SalesReportRawRepository(RawRepositoryBase):
    """매출 리포트 Raw 조회."""

    async def daily_sales(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[RowMapping]:
        """``[start_at, end_at)`` 구간의 일별 주문 수와 총 매출을 집계한다."""
        return await self.fetch_all(
            _DAILY_SALES_SQL,
            {"start_at": start_at, "end_at": end_at},
            query_name=QUERY_DAILY_SALES,
        )

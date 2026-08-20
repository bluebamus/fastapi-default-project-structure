"""SalesReport Raw Repository — 일별 매출 집계 SQL 을 소유한다.

Base(``RawRepositoryBase``)에는 도메인 SQL 을 두지 않는다. SQL 과 컬럼 alias,
그리고 안정적인 ``query_name`` 상수는 이 파일이 소유한다(RAW-REP-002).

이 파일에는 Raw 의 **읽기**(``daily_sales``)와 **쓰기**(``delete_daily_snapshots`` /
``insert_daily_snapshots``)가 나란히 있다. 쓰기 쪽은 커밋하지 않는다 — ``execute`` 는
영향 행 수만 돌려주고, 트랜잭션 경계는 View 본문이 닫는다(TX-001/C-2).

기간 경계에 관하여:
    "종료일 포함" 은 비즈니스 규칙이라 Service 가 해석하고, 여기에는 이미 계산된
    **반열린 구간** ``[start_at, end_at)`` 이 들어온다. ``DATE_ADD(:end, INTERVAL 1 DAY)``
    같은 방언 함수를 SQL 에 넣지 않은 이유이기도 하다 — 규칙이 SQL 에 숨으면
    단위 테스트가 DB 방언에 묶인다(지침서 §4.4).
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from sqlalchemy import RowMapping, text
from sqlalchemy.sql.elements import TextClause

from app.core.repositories.raw_repository_base import (
    RawRepositoryBase,
    resolve_identifier,
    resolve_sort_direction,
)

# 쿼리 이름은 로그의 안정적인 식별자다. 변경하면 대시보드·알람이 끊긴다.
QUERY_DAILY_SALES = "sales_report.daily_sales"
QUERY_DELETE_SNAPSHOTS = "sales_report.delete_daily_snapshots"
QUERY_INSERT_SNAPSHOTS = "sales_report.insert_daily_snapshots"

# 정렬 가능한 컬럼: 요청 키 -> **SELECT 절의 alias**.
#
# 이 매핑이 이 파일에 있는 이유는 alias 를 이 파일이 소유하기 때문이다. View 의
# 쿼리 파라미터에 enum 을 박아도 되지만 그건 UX 이고, 실제 방어선은 SQL 을 만드는
# 여기여야 한다 — Celery 태스크나 스크립트가 이 Repository 를 직접 부를 때도
# 같은 제약이 걸려야 하기 때문이다(RAW-REP-004).
SORTABLE_COLUMNS: Mapping[str, str] = {
    "sales_date": "sales_date",
    "order_count": "order_count",
    "gross_amount": "gross_amount",
}
DEFAULT_SORT_KEY = "sales_date"
DEFAULT_SORT_DIRECTION = "ASC"

# 일별 집계. 값은 전부 named bind parameter 로 들어간다(RAW-REP-003).
# 표준 SQL 만 사용하므로 MySQL·SQLite 양쪽에서 동작한다 — 그래도 MySQL 실제 동작은
# 통합 테스트(@pytest.mark.mysql)가 확인한다(RAW-REP-006).
#
# ORDER BY 만 f-string 자리다. 컬럼명과 정렬 방향은 bind parameter 가 될 수 없어서
# 문자열로 끼워 넣을 수밖에 없는데, **끼워 넣는 값이 요청값이면 injection 이다**.
# 그래서 이 자리에 들어가는 것은 항상 allowlist 를 통과해 나온 코드 상수다.
_DAILY_SALES_SQL_TEMPLATE = """
    SELECT
        DATE(o.created_at) AS sales_date,
        COUNT(*)           AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at <  :end_at
    GROUP BY DATE(o.created_at)
    ORDER BY {order_by} {direction}
"""


# ---------------------------------------------------------------------------
# 쓰기 — 집계 결과를 스냅샷 테이블에 적재한다 (SCN-RAW-003)
# ---------------------------------------------------------------------------
# 왜 Raw 인가:
#     집합 연산이 **서버 안에서 끝나기 때문**이다. ORM 이면 집계 N 행을 파이썬으로
#     끌어와 객체로 만들고 다시 INSERT 로 돌려보내야 한다 — 왕복이 두 번이고, 행 수에
#     비례해 메모리를 먹는다. `INSERT ... SELECT` 는 한 문장으로 DB 안에서 끝난다.
#     "Raw 를 언제 쓰나" 의 답이 이것이다: 집합을 통째로 다룰 때.
#
# 왜 DELETE + INSERT 인가(멱등):
#     같은 기간을 두 번 적재해도 결과가 같아야 한다. MySQL 의
#     `ON DUPLICATE KEY UPDATE` 나 PostgreSQL 의 `ON CONFLICT` 는 방언이라 쓰지 않는다
#     — 표준 SQL 만 쓰면 단위 테스트(SQLite)와 통합 테스트(MySQL)가 같은 문장을 검증한다.
#
# 두 문장이 **한 트랜잭션**이어야 하는 이유:
#     DELETE 만 커밋되고 INSERT 가 실패하면 그 기간의 리포트가 통째로 사라진다.
#     그래서 Repository 는 커밋하지 않고, View 본문이 마지막에 한 번만 커밋한다.
_DELETE_SNAPSHOTS_SQL = text("""
    DELETE FROM sales_daily_snapshots
    WHERE sales_date >= :start_date
      AND sales_date <= :end_date
""")

# generated_at 을 바인드 파라미터로 넣는 이유: 모델의 default 는 ORM/Core 가 발행하는
# 문장에서만 동작한다. Raw DML 은 그것을 우회하므로 값을 SQL 이 명시해야 한다.
# NOW()/CURRENT_TIMESTAMP 를 쓰지 않은 것도 같은 맥락이다 — 시각을 파이썬이 정하면
# 테스트가 시계에 묶이지 않고, 프로젝트의 타임존 설정이 그대로 적용된다.
_INSERT_SNAPSHOTS_SQL = text("""
    INSERT INTO sales_daily_snapshots
        (sales_date, order_count, gross_amount, generated_at)
    SELECT
        DATE(o.created_at),
        COUNT(*),
        COALESCE(SUM(o.total_amount), 0),
        :generated_at
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at <  :end_at
    GROUP BY DATE(o.created_at)
""")


def _daily_sales_statement(order_by: str, direction: str) -> TextClause:
    """정렬이 확정된 집계 SQL 을 만든다.

    Args:
        order_by: **allowlist 를 통과한** SELECT alias.
        direction: ``ASC`` 또는 ``DESC`` (검증 완료).
    """
    return text(_DAILY_SALES_SQL_TEMPLATE.format(order_by=order_by, direction=direction))


class SalesReportRawRepository(RawRepositoryBase):
    """매출 리포트 Raw 조회 및 스냅샷 적재."""

    async def daily_sales(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        sort_by: str = DEFAULT_SORT_KEY,
        sort_direction: str = DEFAULT_SORT_DIRECTION,
    ) -> Sequence[RowMapping]:
        """``[start_at, end_at)`` 구간의 일별 주문 수와 총 매출을 집계한다.

        Args:
            start_at: 구간 시작(포함).
            end_at: 구간 끝(제외).
            sort_by: 정렬 키. ``SORTABLE_COLUMNS`` 의 키여야 한다.
            sort_direction: ``asc``/``desc`` (대소문자 무관).

        Raises:
            ValueError: 허용 목록에 없는 정렬 키·방향. 호출자가 422 로 변환한다.
        """
        # 요청값은 **키로만** 쓴다. SQL 에 들어가는 것은 allowlist 가 돌려준 코드 상수다.
        order_by = resolve_identifier(sort_by, SORTABLE_COLUMNS)
        direction = resolve_sort_direction(sort_direction)

        return await self.fetch_all(
            _daily_sales_statement(order_by, direction),
            {"start_at": start_at, "end_at": end_at},
            query_name=QUERY_DAILY_SALES,
        )

    async def delete_daily_snapshots(self, *, start_date: date, end_date: date) -> int:
        """``[start_date, end_date]`` 구간의 기존 스냅샷을 지운다(커밋하지 않는다).

        재적재의 앞 절반이다. 뒤따르는 INSERT 와 **같은 트랜잭션**이어야 하며,
        커밋 시점은 호출자(View 본문)가 정한다.

        Args:
            start_date: 삭제 시작일(포함).
            end_date: 삭제 종료일(포함).

        Returns:
            지워진 행 수.
        """
        return await self.execute(
            _DELETE_SNAPSHOTS_SQL,
            {"start_date": start_date, "end_date": end_date},
            query_name=QUERY_DELETE_SNAPSHOTS,
        )

    async def insert_daily_snapshots(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        generated_at: datetime,
    ) -> int:
        """``[start_at, end_at)`` 구간의 일별 집계를 스냅샷 테이블에 적재한다.

        집계와 적재가 한 문장이라 결과 행이 파이썬으로 올라오지 않는다.

        Args:
            start_at: 집계 구간 시작(포함).
            end_at: 집계 구간 끝(제외).
            generated_at: 적재 시각 — Raw DML 이라 SQL 이 명시해야 한다.

        Returns:
            적재된 행 수(= 매출이 있었던 날의 수).
        """
        return await self.execute(
            _INSERT_SNAPSHOTS_SQL,
            {"start_at": start_at, "end_at": end_at, "generated_at": generated_at},
            query_name=QUERY_INSERT_SNAPSHOTS,
        )

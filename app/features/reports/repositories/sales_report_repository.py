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
    단위 테스트가 DB 방언에 묶인다(docs/guides/DEVELOPMENT.md §6.4).

시각과 영업일에 관하여 (service-hardening ADR-010):
    ``created_at`` 은 UTC 로 저장된다. 구간 경계는 Service 가 로컬 영업일(TIME_ZONE)을 UTC
    순간으로 바꿔 넘기고, 시각 바인드는 ``UTCDateTime`` 타입을 거친다(naive 거부 · UTC 변환).
    일자 묶음만은 SQL 이 로컬 날짜로 바꿔야 해서 방언 함수가 필요하다 — MySQL 은
    ``CONVERT_TZ``, SQLite 는 ``DATE(값, '+N minutes')``. 방언별 식은 ``_LOCAL_DATE_SQL`` 한 곳에 둔다.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

from sqlalchemy import RowMapping, bindparam, text
from sqlalchemy.sql.elements import TextClause

from app.core.models.types import UTCDateTime
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

# UTC 로 저장된 ``created_at`` 을 로컬 영업일로 묶는 식(방언별). ``:tz_offset`` 은
# ``_offset_param`` 이 방언에 맞춰 만든 문자열이다(MySQL ``+09:00`` · SQLite ``+540 minutes``).
#
# ponytail: 고정 오프셋 — 구간 시작 시점의 TIME_ZONE 오프셋 하나로 모든 행을 묶는다. DST 가 있는
# 지역은 전환일 앞뒤가 하루 어긋난다. 그런 TIME_ZONE 이 필요해지면 행마다 바꾸는 named time zone
# (``CONVERT_TZ(col, '+00:00', 'Europe/Berlin')`` + MySQL 시간대 테이블 적재)으로 올린다
# (residual-risk R-003). 기본 Asia/Seoul 은 DST 가 없다.
_LOCAL_DATE_SQL: Mapping[str, str] = {
    "mysql": "DATE(CONVERT_TZ(o.created_at, '+00:00', :tz_offset))",
    "sqlite": "DATE(o.created_at, :tz_offset)",
}

# 시각 바인드는 ``UTCDateTime`` 을 거친다 — Raw ``text()`` 는 컬럼 타입을 모르므로 지정하지
# 않으면 드라이버가 aware 값의 오프셋을 버리고 벽시계만 보낸다(9시간 어긋남).
_START_AT = bindparam("start_at", type_=UTCDateTime())
_END_AT = bindparam("end_at", type_=UTCDateTime())
_GENERATED_AT = bindparam("generated_at", type_=UTCDateTime())

# 일별 집계. 값은 전부 named bind parameter 로 들어간다(RAW-REP-003).
# 일자 묶음 식만 방언 함수다(위 ``_LOCAL_DATE_SQL``) — MySQL 실제 동작은
# 통합 테스트(@pytest.mark.mysql)가 확인한다(RAW-REP-006).
#
# ORDER BY 와 일자 식만 f-string 자리다. 컬럼명과 정렬 방향은 bind parameter 가 될 수 없어서
# 문자열로 끼워 넣을 수밖에 없는데, **끼워 넣는 값이 요청값이면 injection 이다**.
# 그래서 이 자리에 들어가는 것은 항상 allowlist 를 통과해 나온 코드 상수다.
_DAILY_SALES_SQL_TEMPLATE = """
    SELECT
        {local_date} AS sales_date,
        COUNT(*)           AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at <  :end_at
    GROUP BY {local_date}
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
# 테스트가 시계에 묶이지 않고, 저장 시각이 UTC 라는 규칙(ADR-010)이 그대로 적용된다.
#
# ponytail: 고정 오프셋 — 조회 SQL 과 같은 한계다(``_LOCAL_DATE_SQL`` 주석, residual-risk R-003).
_INSERT_SNAPSHOTS_SQL_TEMPLATE = """
    INSERT INTO sales_daily_snapshots
        (sales_date, order_count, gross_amount, generated_at)
    SELECT
        {local_date},
        COUNT(*),
        COALESCE(SUM(o.total_amount), 0),
        :generated_at
    FROM sales_orders AS o
    WHERE o.created_at >= :start_at
      AND o.created_at <  :end_at
    GROUP BY {local_date}
"""


def _local_date_sql(dialect_name: str) -> str:
    try:
        return _LOCAL_DATE_SQL[dialect_name]
    except KeyError:
        raise NotImplementedError(
            f"로컬 영업일 집계 식이 없는 방언입니다: {dialect_name}"
        ) from None


def _offset_param(dialect_name: str, offset: timedelta) -> str:
    """UTC 오프셋을 방언의 일자 식이 받는 문자열로 바꾼다.

    MySQL ``CONVERT_TZ`` 는 ``+09:00``/``-05:30``, SQLite 날짜 수정자는 ``+540 minutes``.
    """
    minutes = int(offset.total_seconds() // 60)
    if dialect_name == "sqlite":
        return f"{minutes:+d} minutes"
    sign = "+" if minutes >= 0 else "-"
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{rest:02d}"


def _daily_sales_statement(order_by: str, direction: str, dialect_name: str) -> TextClause:
    """정렬이 확정된 집계 SQL 을 만든다.

    Args:
        order_by: **allowlist 를 통과한** SELECT alias.
        direction: ``ASC`` 또는 ``DESC`` (검증 완료).
        dialect_name: 일자 식을 고를 방언 이름(코드 상수 표에서만 고른다).
    """
    sql = _DAILY_SALES_SQL_TEMPLATE.format(
        local_date=_local_date_sql(dialect_name), order_by=order_by, direction=direction
    )
    return text(sql).bindparams(_START_AT, _END_AT)


def _insert_snapshots_statement(dialect_name: str) -> TextClause:
    sql = _INSERT_SNAPSHOTS_SQL_TEMPLATE.format(local_date=_local_date_sql(dialect_name))
    return text(sql).bindparams(_START_AT, _END_AT, _GENERATED_AT)


class SalesReportRawRepository(RawRepositoryBase):
    """매출 리포트 Raw 조회 및 스냅샷 적재."""

    def _dialect_name(self) -> str:
        return self.db_session.get_bind().dialect.name

    async def daily_sales(
        self,
        *,
        start_at: datetime,
        end_at: datetime,
        tz_offset: timedelta,
        sort_by: str = DEFAULT_SORT_KEY,
        sort_direction: str = DEFAULT_SORT_DIRECTION,
    ) -> Sequence[RowMapping]:
        """``[start_at, end_at)`` 구간의 일별 주문 수와 총 매출을 로컬 영업일로 집계한다.

        Args:
            start_at: 구간 시작(포함, aware).
            end_at: 구간 끝(제외, aware).
            tz_offset: 일자를 나눌 로컬 UTC 오프셋(고정 — ``_LOCAL_DATE_SQL`` 주석).
            sort_by: 정렬 키. ``SORTABLE_COLUMNS`` 의 키여야 한다.
            sort_direction: ``asc``/``desc`` (대소문자 무관).

        Raises:
            ValueError: 허용 목록에 없는 정렬 키·방향. 호출자가 422 로 변환한다.
        """
        # 요청값은 **키로만** 쓴다. SQL 에 들어가는 것은 allowlist 가 돌려준 코드 상수다.
        order_by = resolve_identifier(sort_by, SORTABLE_COLUMNS)
        direction = resolve_sort_direction(sort_direction)

        dialect_name = self._dialect_name()
        return await self.fetch_all(
            _daily_sales_statement(order_by, direction, dialect_name),
            {
                "start_at": start_at,
                "end_at": end_at,
                "tz_offset": _offset_param(dialect_name, tz_offset),
            },
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
        tz_offset: timedelta,
        generated_at: datetime,
    ) -> int:
        """``[start_at, end_at)`` 구간의 일별 집계(로컬 영업일)를 스냅샷 테이블에 적재한다.

        집계와 적재가 한 문장이라 결과 행이 파이썬으로 올라오지 않는다.

        Args:
            start_at: 집계 구간 시작(포함, aware).
            end_at: 집계 구간 끝(제외, aware).
            tz_offset: 일자를 나눌 로컬 UTC 오프셋.
            generated_at: 적재 시각(aware) — Raw DML 이라 SQL 이 명시해야 한다.

        Returns:
            적재된 행 수(= 매출이 있었던 날의 수).
        """
        dialect_name = self._dialect_name()
        return await self.execute(
            _insert_snapshots_statement(dialect_name),
            {
                "start_at": start_at,
                "end_at": end_at,
                "tz_offset": _offset_param(dialect_name, tz_offset),
                "generated_at": generated_at,
            },
            query_name=QUERY_INSERT_SNAPSHOTS,
        )

"""Report Service — 매출 리포트 유스케이스.

기간 규칙(종료일 포함, 최대 조회 범위)은 비즈니스 규칙이므로 여기 있고,
SQL 과 컬럼 alias 는 Repository 가 소유한다(지침서 §4.4).
Raw 결과는 **여기서** Pydantic DTO 로 검증해 밖으로 내보낸다(RAW-REP-005).

읽기(``get_daily_sales``)와 쓰기(``refresh_daily_snapshots``)가 같은 규칙을 따른다 —
기간 해석은 이 계층, SQL 은 Repository, 커밋은 View 본문.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.exceptions import InvalidDateRangeException, InvalidSortException
from app.features.reports.repositories.sales_report_repository import (
    DEFAULT_SORT_DIRECTION,
    DEFAULT_SORT_KEY,
    SORTABLE_COLUMNS,
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import (
    DailySalesItem,
    DailySnapshotLoadResponse,
)
from config import timezone_settings

# 한 번에 집계할 수 있는 최대 일수. 무제한 범위는 실행 계획이 급격히 나빠진다(NFR-002).
MAX_REPORT_DAYS = 366


class ReportService(BaseService):
    """매출 리포트 비즈니스 로직 (DB 세션 기반)."""

    def __init__(self, db_session: AsyncSession) -> None:
        super().__init__(db_session)
        self.repository = SalesReportRawRepository(db_session)

    async def get_daily_sales(
        self,
        *,
        start_date: date,
        end_date: date,
        sort_by: str = DEFAULT_SORT_KEY,
        sort_direction: str = DEFAULT_SORT_DIRECTION,
    ) -> list[DailySalesItem]:
        """지정 기간(종료일 포함)의 일별 매출을 집계한다."""
        self._validate_range(start_date, end_date)

        # "종료일 포함" 을 반열린 구간 [start, end+1일) 로 바꾼다. 종료일의 23:59:59
        # 같은 값을 쓰면 마이크로초 단위 주문을 놓친다.
        start_at = datetime.combine(start_date, time.min)
        end_at = datetime.combine(end_date + timedelta(days=1), time.min)

        try:
            rows = await self.repository.daily_sales(
                start_at=start_at,
                end_at=end_at,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
        except ValueError as error:
            # Repository 의 allowlist 는 SQL 안전을 위한 장치라 ValueError 만 던진다.
            # HTTP 의미(422)를 붙이는 것은 유스케이스를 아는 이 계층의 몫이다.
            raise InvalidSortException(
                detail={
                    "sort_by": sort_by,
                    "sort_direction": sort_direction,
                    "allowed_sort_by": sorted(SORTABLE_COLUMNS),
                    "allowed_sort_direction": ["asc", "desc"],
                },
            ) from error

        # RowMapping 은 dict 가 아니다 — 명시적으로 변환해 검증한다.
        return [DailySalesItem.model_validate(dict(row)) for row in rows]

    async def refresh_daily_snapshots(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> DailySnapshotLoadResponse:
        """지정 기간(종료일 포함)의 일별 매출을 스냅샷 테이블에 재적재한다.

        원장(``sales_orders``)은 읽기만 한다 — 불변 원장이라 고치지 않는다. 바뀌는 것은
        집계 결과 테이블뿐이다.

        멱등이다: 같은 기간을 두 번 불러도 결과가 같다. 기존 행을 지우고 다시 넣기
        때문이며, 두 문장이 한 트랜잭션이라 중간 상태가 밖에서 보이지 않는다.

        **커밋하지 않는다.** 호출자(View 본문)가 응답 직전에 한 번 커밋한다(TX-001).
        """
        self._validate_range(start_date, end_date)

        start_at = datetime.combine(start_date, time.min)
        end_at = datetime.combine(end_date + timedelta(days=1), time.min)
        generated_at = timezone_settings.now()

        # 순서가 중요하다 — 지우고 나서 넣는다. 반대로 하면 방금 넣은 것을 지운다.
        deleted = await self.repository.delete_daily_snapshots(
            start_date=start_date,
            end_date=end_date,
        )
        inserted = await self.repository.insert_daily_snapshots(
            start_at=start_at,
            end_at=end_at,
            generated_at=generated_at,
        )

        self.log.info(
            "매출 스냅샷 적재 %s~%s 삭제=%d 적재=%d",
            start_date,
            end_date,
            deleted,
            inserted,
        )
        return DailySnapshotLoadResponse(
            start_date=start_date,
            end_date=end_date,
            deleted=deleted,
            inserted=inserted,
            generated_at=generated_at,
        )

    @staticmethod
    def _validate_range(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidDateRangeException(
                message="종료일은 시작일보다 앞설 수 없습니다.",
                detail={"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            )

        span = (end_date - start_date).days + 1
        if span > MAX_REPORT_DAYS:
            raise InvalidDateRangeException(
                message=f"한 번에 조회할 수 있는 기간은 최대 {MAX_REPORT_DAYS}일입니다.",
                detail={"requested_days": span, "max_days": MAX_REPORT_DAYS},
            )

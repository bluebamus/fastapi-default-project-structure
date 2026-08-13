"""Report Service — 매출 리포트 유스케이스.

기간 규칙(종료일 포함, 최대 조회 범위)은 비즈니스 규칙이므로 여기 있고,
SQL 과 컬럼 alias 는 Repository 가 소유한다(지침서 §4.4).
Raw 결과는 **여기서** Pydantic DTO 로 검증해 밖으로 내보낸다(RAW-REP-005).
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import DailySalesItem

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
    ) -> list[DailySalesItem]:
        """지정 기간(종료일 포함)의 일별 매출을 집계한다."""
        self._validate_range(start_date, end_date)

        # "종료일 포함" 을 반열린 구간 [start, end+1일) 로 바꾼다. 종료일의 23:59:59
        # 같은 값을 쓰면 마이크로초 단위 주문을 놓친다.
        start_at = datetime.combine(start_date, time.min)
        end_at = datetime.combine(end_date + timedelta(days=1), time.min)

        rows = await self.repository.daily_sales(start_at=start_at, end_at=end_at)
        # RowMapping 은 dict 가 아니다 — 명시적으로 변환해 검증한다.
        return [DailySalesItem.model_validate(dict(row)) for row in rows]

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

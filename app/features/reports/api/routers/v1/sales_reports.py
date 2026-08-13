"""일별 매출 리포트 View (v1) — Raw SQL workflow 참조 예제.

``app/features/catalog`` 의 ORM 예제와 나란히 놓고 비교하면, 달라지는 것은
Repository 구현뿐임을 알 수 있다. Dependency 조립·Service 호출·Pydantic 응답·
OpenAPI 메타데이터는 동일하다.

조회이므로 커밋하지 않는다.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.exception import ErrorResponse
from app.features.reports.dependencies.report_dependencies import (
    get_report_service_readonly,
)
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/sales/daily",
    response_model=DailySalesReportResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "조회 기간이 올바르지 않음(역순 기간 또는 최대 일수 초과)",
        },
    },
    summary="일별 매출 리포트",
    description=(
        "지정한 기간의 주문 수와 총 매출을 **일별로 집계**합니다. "
        "종료일은 조회 범위에 포함되며, 매출이 없는 날은 결과에 나타나지 않습니다."
    ),
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(description="조회 시작일(포함)", examples=["2026-08-01"]),
    end_date: date = Query(description="조회 종료일(포함)", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(start_date=start_date, end_date=end_date)
    return DailySalesReportResponse(
        start_date=start_date,
        end_date=end_date,
        items=items,
    )

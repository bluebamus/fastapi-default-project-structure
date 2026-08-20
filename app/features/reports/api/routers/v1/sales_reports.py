"""일별 매출 리포트 View (v1) — Raw SQL workflow 참조 예제.

``app/features/catalog`` 의 ORM 예제와 나란히 놓고 비교하면, 달라지는 것은
Repository 구현뿐임을 알 수 있다. Dependency 조립·Service 호출·Pydantic 응답·
OpenAPI 메타데이터는 동일하다.

이 파일에는 Raw 의 읽기와 쓰기가 둘 다 있다:
    - ``GET  /sales/daily``            조회 — read-only 세션, 커밋 없음
    - ``POST /sales/daily/snapshots``  적재 — writer 세션, **본문에서 1회 커밋**

커밋이 View 본문에 있는 이유는 FastAPI 의 yield 의존성 정리(teardown)가 **응답을
보낸 뒤에** 돌기 때문이다. 커밋을 거기에 두면 실패해도 이미 성공 응답이 나간 뒤라
클라이언트는 저장됐다고 믿는다(TX-001).
"""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.core.exception import ErrorResponse
from app.features.reports.dependencies.report_dependencies import (
    get_report_service,
    get_report_service_readonly,
)
from app.features.reports.repositories.sales_report_repository import (
    DEFAULT_SORT_KEY,
    SORTABLE_COLUMNS,
)
from app.features.reports.schemas.report_schema import (
    DailySalesReportResponse,
    DailySnapshotLoadRequest,
    DailySnapshotLoadResponse,
)
from app.features.reports.services.report_service import ReportService

router = APIRouter()


@router.get(
    "/sales/daily",
    response_model=DailySalesReportResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": (
                "조회 기간이 올바르지 않음(역순 기간 또는 최대 일수 초과), "
                "또는 정렬 키·방향이 허용 목록에 없음"
            ),
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
    sort_by: str = Query(
        DEFAULT_SORT_KEY,
        description=f"정렬 키. 허용: {', '.join(sorted(SORTABLE_COLUMNS))}",
        examples=["gross_amount"],
    ),
    sort_direction: str = Query(
        "asc",
        description="정렬 방향(asc/desc)",
        examples=["desc"],
    ),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    items = await service.get_daily_sales(
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    return DailySalesReportResponse(
        start_date=start_date,
        end_date=end_date,
        items=items,
    )


# 201 이 아니라 200 인 이유: 새 URL 을 만드는 생성이 아니라 기존 기간을 통째로
# 대체하는 멱등 연산이다. 두 번 호출해도 같은 상태가 되므로 Location 이 없다.
@router.post(
    "/sales/daily/snapshots",
    response_model=DailySnapshotLoadResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "적재 기간이 올바르지 않음(역순 기간 또는 최대 일수 초과)",
        },
    },
    summary="일별 매출 스냅샷 적재",
    description=(
        "지정한 기간의 일별 매출 집계를 스냅샷 테이블에 **재적재**합니다. "
        "같은 기간을 여러 번 호출해도 결과가 같습니다(멱등). "
        "주문 원장은 읽기만 하며 변경되지 않습니다."
    ),
    operation_id="loadDailySalesSnapshots",
)
async def load_daily_sales_snapshots(
    payload: DailySnapshotLoadRequest,
    service: ReportService = Depends(get_report_service),
) -> DailySnapshotLoadResponse:
    result = await service.refresh_daily_snapshots(
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    # DELETE 와 INSERT 를 한 번에 확정한다. 응답을 만들기 전에 정확히 한 번 커밋한다 —
    # 여기서 실패하면 200 이 나가지 않고, 지운 것도 함께 롤백된다.
    await service.commit()
    return result

"""Reports 도메인 스키마 — Raw 집계 결과의 외부 계약 (Pydantic v2).

Raw 결과는 ORM 객체가 아니므로 ``from_attributes`` 에 의존하지 않는다.
``RowMapping`` 을 명시적으로 ``dict`` 로 바꿔 검증한다(RAW-REP-005).
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DailySalesItem(BaseModel):
    """하루치 매출 집계 한 줄."""

    sales_date: date = Field(description="매출 일자", examples=["2026-08-01"])
    order_count: int = Field(ge=0, description="주문 수", examples=[42])
    gross_amount: Decimal = Field(ge=0, description="총 매출", examples=["5120.50"])


class DailySalesReportResponse(BaseModel):
    """일별 매출 리포트 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "items": [
                        {
                            "sales_date": "2026-08-01",
                            "order_count": 42,
                            "gross_amount": "5120.50",
                        }
                    ],
                }
            ]
        }
    )

    start_date: date = Field(description="조회 시작일(포함)")
    end_date: date = Field(description="조회 종료일(포함)")
    items: list[DailySalesItem] = Field(description="일자별 집계. 매출이 없는 날은 포함되지 않는다")


class DailySnapshotLoadResponse(BaseModel):
    """스냅샷 적재 결과 — Raw 쓰기 예제의 응답.

    조회 응답과 달리 **무엇이 얼마나 바뀌었는지**를 돌려준다. Raw DML 의 영향 행 수는
    호출자가 결과를 판단할 수 있는 유일한 신호라, 삼켜서는 안 된다.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "start_date": "2026-08-01",
                    "end_date": "2026-08-07",
                    "deleted": 3,
                    "inserted": 5,
                    "generated_at": "2026-08-20T09:00:00+09:00",
                }
            ]
        }
    )

    start_date: date = Field(description="적재 대상 시작일(포함)")
    end_date: date = Field(description="적재 대상 종료일(포함)")
    deleted: int = Field(ge=0, description="재적재를 위해 지운 기존 스냅샷 행 수")
    inserted: int = Field(ge=0, description="새로 적재한 행 수 (= 매출이 있었던 날의 수)")
    generated_at: datetime = Field(description="적재 시각")


class DailySnapshotLoadRequest(BaseModel):
    """스냅샷 적재 요청.

    조회는 쿼리 파라미터, 적재는 본문이다 — POST 의 대상은 "무엇을 적재할지" 라는
    명세이지 URL 의 일부가 아니다. 본문으로 두면 필드가 늘어도 계약이 흔들리지 않는다.
    """

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"start_date": "2026-08-01", "end_date": "2026-08-07"}]}
    )

    start_date: date = Field(description="적재 대상 시작일(포함)")
    end_date: date = Field(description="적재 대상 종료일(포함)")
